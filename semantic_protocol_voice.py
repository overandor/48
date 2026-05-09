#!/usr/bin/env python3
"""
semantic_protocol_voice.py

Voice-first wrapper for the Semantic Protocol Runtime.

Goal
----
Talk to the terminal, have the terminal talk back, and route spoken intent into
an inspectable semantic protocol plan before execution.

Run:
    python semantic_protocol_voice.py

Optional:
    python semantic_protocol_voice.py --runtime semantic_protocol_runtime.py
    python semantic_protocol_voice.py --tts espeak
    python semantic_protocol_voice.py --stt speechrecognition
    python semantic_protocol_voice.py --execute

Design notes
------------
- Default mode is safe: explain / dry-run first.
- Speech-to-text is pluggable and falls back to typed input when local audio
  packages are unavailable.
- Text-to-speech is pluggable and falls back to printed output.
- The NL-to-protocol compiler is intentionally bounded and deterministic.
  Replace `compile_intent_to_protocol` with a local LLM later if desired.
"""

from __future__ import annotations

import argparse
import os
import pathlib
import platform
import shlex
import subprocess
import sys
import tempfile
import textwrap
from dataclasses import dataclass
from typing import Optional, Tuple


DEFAULT_RUNTIME = "semantic_protocol_runtime.py"
DEFAULT_DB = "db.main"
DEFAULT_FILE = "hot_users.jsonl"
DEFAULT_SLACK = "#risk"


@dataclass
class VoiceConfig:
    runtime: str
    stt: str
    tts: str
    execute: bool
    keep_protocols: bool
    workdir: pathlib.Path


@dataclass
class CompiledIntent:
    protocol: str
    explanation: str
    requires_confirmation: bool = True


def say(text: str, cfg: VoiceConfig) -> None:
    """Speak text if possible, always print it."""
    print(f"\nSPR Voice: {text}\n")
    engine = cfg.tts.lower()
    if engine == "none":
        return

    if engine in {"auto", "espeak"}:
        try:
            subprocess.run(["espeak-ng", text], check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            return
        except FileNotFoundError:
            if engine == "espeak":
                return

    if engine in {"auto", "say"} and platform.system() == "Darwin":
        try:
            subprocess.run(["say", text], check=False)
            return
        except FileNotFoundError:
            if engine == "say":
                return

    if engine in {"auto", "pyttsx3"}:
        try:
            import pyttsx3  # type: ignore
            speaker = pyttsx3.init()
            speaker.say(text)
            speaker.runAndWait()
            return
        except Exception:
            return


def listen(cfg: VoiceConfig) -> str:
    """Listen using a local STT backend, or fall back to keyboard input."""
    backend = cfg.stt.lower()

    if backend in {"auto", "speechrecognition", "sr"}:
        try:
            import speech_recognition as sr  # type: ignore
            recognizer = sr.Recognizer()
            with sr.Microphone() as source:
                print("Listening... speak now.")
                recognizer.adjust_for_ambient_noise(source, duration=0.4)
                audio = recognizer.listen(source, timeout=8, phrase_time_limit=18)
            try:
                text = recognizer.recognize_google(audio)
                print(f"You: {text}")
                return text
            except Exception:
                # Prefer offline Sphinx when installed; otherwise type fallback.
                try:
                    text = recognizer.recognize_sphinx(audio)
                    print(f"You: {text}")
                    return text
                except Exception:
                    pass
        except Exception as exc:
            if backend not in {"auto"}:
                print(f"[voice] speech_recognition unavailable: {exc}")

    # Text fallback keeps the system usable on servers and CI.
    return input("You/type command: ").strip()


def is_yes(text: str) -> bool:
    return text.strip().lower() in {"y", "yes", "yeah", "yep", "proceed", "run", "execute", "do it", "confirm"}


def is_no(text: str) -> bool:
    return text.strip().lower() in {"n", "no", "nope", "cancel", "stop", "abort"}


def compile_intent_to_protocol(intent: str) -> CompiledIntent:
    """
    Deterministic bounded NL-to-protocol compiler.

    This is intentionally conservative: it recognizes a small set of workflow
    intents and converts them into explicit semantic protocol text. If the user
    already speaks or pastes SPR syntax, it passes it through.
    """
    raw = intent.strip()
    lower = raw.lower()

    # User supplied direct SPR source.
    if "policy" in lower and (":=" in raw or "!" in raw):
        return CompiledIntent(
            protocol=raw,
            explanation="I detected direct semantic protocol syntax and will use it as the source of truth.",
        )

    # Canonical demo from the conversation.
    high_score_terms = ["high-scoring", "high scoring", "hot users", "score above", "score greater", "score >"]
    if any(term in lower for term in high_score_terms) and "user" in lower:
        threshold = "0.8"
        import re
        m = re.search(r"(?:above|greater than|score >|score greater than)\s*([0-9.]+)", lower)
        if m:
            threshold = m.group(1)

        output_file = DEFAULT_FILE
        m = re.search(r"(?:save|write|export).*?(?:to|as)\s+([A-Za-z0-9_./-]+\.(?:jsonl|json|csv|txt))", lower)
        if m:
            output_file = m.group(1)

        slack_channel = DEFAULT_SLACK
        m = re.search(r"#([A-Za-z0-9_-]+)", raw)
        if m:
            slack_channel = f"#{m.group(1)}"

        protocol = f"""
        policy {{
          optimize: latency > cost
          deterministic: true
          allow database[{DEFAULT_DB}]
          allow filesystem[*]
          allow network[slack.ops]
          deny shell[*]
        }}

        users := source @{DEFAULT_DB} "select id, email, score from users"
        hot   := users -> filter score > {threshold} -> project [id, email, score]
        write! hot @file:"{output_file}"
        notify! hot @slack.ops:"{slack_channel}"
        """
        explanation = (
            f"I understood this as: read users from {DEFAULT_DB}, filter score above {threshold}, "
            f"project id, email, and score, write to {output_file}, then notify {slack_channel}."
        )
        return CompiledIntent(textwrap.dedent(protocol).strip(), explanation)

    # File export intent.
    if ("save" in lower or "write" in lower or "export" in lower) and "file" in lower:
        protocol = f"""
        policy {{
          optimize: latency > cost
          deterministic: true
          allow filesystem[*]
          deny shell[*]
        }}

        input := source @file "input.jsonl"
        out   := input -> project [*]
        write! out @file:"output.jsonl"
        """
        return CompiledIntent(
            textwrap.dedent(protocol).strip(),
            "I created a conservative file-export protocol. Edit the generated source if you want a different input or output file.",
        )

    # Unknown intent: create a safe skeleton, no side effects.
    protocol = f"""
    policy {{
      optimize: latency > cost
      deterministic: true
      deny shell[*]
      deny network[*]
    }}

    note := source @file "intent.txt"
    result := note -> project [*]
    """
    return CompiledIntent(
        textwrap.dedent(protocol).strip(),
        "I could not safely infer a complete executable protocol. I created a no-network, no-shell skeleton. Please refine the intent.",
        requires_confirmation=False,
    )


def runtime_command(cfg: VoiceConfig, protocol_path: pathlib.Path, action: str) -> list[str]:
    py = sys.executable or "python"
    if action == "explain":
        return [py, cfg.runtime, "explain", str(protocol_path)]
    if action == "dry-run":
        return [py, cfg.runtime, "run", str(protocol_path), "--dry-run"]
    if action == "run":
        return [py, cfg.runtime, "run", str(protocol_path)]
    raise ValueError(action)


def run_runtime(cfg: VoiceConfig, protocol: str, action: str) -> Tuple[int, str]:
    cfg.workdir.mkdir(parents=True, exist_ok=True)
    if cfg.keep_protocols:
        fd, path = tempfile.mkstemp(prefix="spr_voice_", suffix=".spr", dir=str(cfg.workdir))
        os.close(fd)
        protocol_path = pathlib.Path(path)
        protocol_path.write_text(protocol, encoding="utf-8")
    else:
        tmp = tempfile.NamedTemporaryFile("w", suffix=".spr", delete=False, encoding="utf-8")
        tmp.write(protocol)
        tmp.close()
        protocol_path = pathlib.Path(tmp.name)

    cmd = runtime_command(cfg, protocol_path, action)
    try:
        proc = subprocess.run(cmd, text=True, capture_output=True)
        output = ""
        if proc.stdout:
            output += proc.stdout
        if proc.stderr:
            output += "\n[stderr]\n" + proc.stderr
        return proc.returncode, output.strip()
    finally:
        if not cfg.keep_protocols:
            try:
                protocol_path.unlink(missing_ok=True)
            except Exception:
                pass


def print_protocol(protocol: str) -> None:
    print("\n--- GENERATED SEMANTIC PROTOCOL ---")
    print(protocol)
    print("--- END PROTOCOL ---\n")


def voice_loop(cfg: VoiceConfig) -> None:
    say(
        "Semantic Protocol voice mode is ready. Tell me a workflow, or say help, quit, or repl.",
        cfg,
    )
    while True:
        try:
            utterance = listen(cfg)
        except (KeyboardInterrupt, EOFError):
            say("Stopping voice mode.", cfg)
            return

        if not utterance:
            continue
        lower = utterance.strip().lower()
        if lower in {"quit", "exit", "stop", "goodbye"}:
            say("Stopping voice mode.", cfg)
            return
        if lower == "help":
            say(
                "Try: get all high-scoring users from the database and save them to a file, then notify the team on Slack.",
                cfg,
            )
            continue
        if lower == "repl":
            say("Launching the existing text REPL.", cfg)
            subprocess.run([sys.executable, cfg.runtime, "repl"], check=False)
            continue

        compiled = compile_intent_to_protocol(utterance)
        say(compiled.explanation, cfg)
        print_protocol(compiled.protocol)

        code, explanation = run_runtime(cfg, compiled.protocol, "explain")
        if code == 0:
            say("Here is the execution plan. I will show it in the terminal.", cfg)
            print(explanation)
        else:
            say("The runtime could not explain the generated protocol. Check the terminal output.", cfg)
            print(explanation)
            continue

        if not compiled.requires_confirmation:
            continue

        if cfg.execute:
            say("Execution mode is enabled. Do you want me to run this for real?", cfg)
        else:
            say("Default is dry run. Do you want me to dry-run this plan?", cfg)

        confirm = listen(cfg)
        if is_no(confirm):
            say("Cancelled. No execution happened.", cfg)
            continue
        if not is_yes(confirm):
            say("I did not hear a clear confirmation, so I will not run it.", cfg)
            continue

        action = "run" if cfg.execute else "dry-run"
        code, output = run_runtime(cfg, compiled.protocol, action)
        print(output)
        if code == 0:
            say("Done. The semantic protocol completed successfully.", cfg)
        else:
            say("The semantic protocol failed. I printed the error output.", cfg)


def parse_args(argv: Optional[list[str]] = None) -> VoiceConfig:
    parser = argparse.ArgumentParser(description="Voice-first terminal wrapper for Semantic Protocol Runtime")
    parser.add_argument("--runtime", default=DEFAULT_RUNTIME, help="Path to semantic_protocol_runtime.py")
    parser.add_argument("--stt", default="auto", choices=["auto", "speechrecognition", "sr", "text"], help="Speech-to-text backend")
    parser.add_argument("--tts", default="auto", choices=["auto", "none", "espeak", "pyttsx3", "say"], help="Text-to-speech backend")
    parser.add_argument("--execute", action="store_true", help="Run protocols for real after confirmation instead of dry-run")
    parser.add_argument("--keep-protocols", action="store_true", help="Keep generated .spr files in .spr_voice/")
    parser.add_argument("--workdir", default=".spr_voice", help="Directory for generated protocol files when --keep-protocols is enabled")
    args = parser.parse_args(argv)
    return VoiceConfig(
        runtime=args.runtime,
        stt=args.stt,
        tts=args.tts,
        execute=args.execute,
        keep_protocols=args.keep_protocols,
        workdir=pathlib.Path(args.workdir),
    )


if __name__ == "__main__":
    config = parse_args()
    if config.stt == "text":
        print("[voice] STT is set to text mode; type instead of speaking.")
    voice_loop(config)

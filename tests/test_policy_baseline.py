import textwrap

import pytest

from semantic_protocol_runtime import GraphBuilder, PolicyError, ProgramParser, ProgramVerifier


def parse_and_verify(source: str):
    program = ProgramParser().parse(textwrap.dedent(source).strip())
    graph = GraphBuilder().build(program)
    ProgramVerifier().verify_static(program, graph)
    return program


def test_policy_allows_file_write_when_filesystem_allowed():
    parse_and_verify(
        '''
        policy {
          deterministic: true
          allow database[db.main]
          allow filesystem[*]
          deny network[*]
          deny shell[*]
        }

        users := source @db.main "select id, email, score from users"
        hot := users -> filter score > 0.8
        write! hot @file:"hot_users.jsonl"
        '''
    )


def test_policy_denies_slack_when_network_denied():
    with pytest.raises(PolicyError):
        parse_and_verify(
            '''
            policy {
              deterministic: true
              allow database[db.main]
              allow filesystem[*]
              deny network[*]
              deny shell[*]
            }

            users := source @db.main "select id, email, score from users"
            hot := users -> filter score > 0.8
            notify! hot @slack.ops:"#risk"
            '''
        )

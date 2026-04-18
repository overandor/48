import unittest
import os
import sys
import shutil
from semantic_protocol_runtime import ProgramParser, Planner, PythonLowerer, SemanticProtocolCompiler, Program, TypeRef, TransformOp

class TestProgramParser(unittest.TestCase):
    def setUp(self):
        self.parser = ProgramParser()

    def test_parse_simple(self):
        text = """
        users := source @db.main "select * from users"
        hot := users -> filter score > 0.8
        """
        prog = self.parser.parse(text)
        self.assertEqual(len(prog.bindings), 2)
        self.assertEqual(prog.bindings[0].name, "users")
        self.assertEqual(prog.bindings[1].name, "hot")
        self.assertEqual(prog.bindings[1].input_name, "users")

    def test_parse_join_fallback(self):
        text = """
        a := source @db "select 1"
        b := source @db "select 2"
        c := a & b
        d := c | a
        """
        prog = self.parser.parse(text)
        self.assertEqual(prog.bindings[2].ops[0].name, "join")
        self.assertEqual(prog.bindings[3].ops[0].name, "fallback")

    def test_parse_types(self):
        text = "res : List[Map[String, Int]] := source @db 'select 1'"
        prog = self.parser.parse(text)
        t = prog.bindings[0].declared_type
        self.assertEqual(t.base, "List")
        self.assertEqual(t.params[0].base, "Map")
        self.assertEqual(t.params[0].params[1].base, "Int")

class TestPlanner(unittest.TestCase):
    def setUp(self):
        self.planner = Planner()

    def test_basic_plan(self):
        prog = Program()
        # Minimal manual program construction or use parser
        parser = ProgramParser()
        prog = parser.parse('u := source @db "select 1"')
        plan = self.planner.build_plan(prog)
        self.assertEqual(len(plan.steps), 1)
        self.assertEqual(plan.steps[0].runtime, "sql:source")

class TestPythonLowerer(unittest.TestCase):
    def setUp(self):
        self.lowerer = PythonLowerer()

    def test_lower_basic(self):
        parser = ProgramParser()
        prog = parser.parse('u := source @db "select 1"')
        script = self.lowerer.lower_python_script(prog)
        self.assertIn('DATA["u"] = _spr_fetch_db_rows', script)

class TestIntegration(unittest.TestCase):
    def test_full_compile(self):
        compiler = SemanticProtocolCompiler()
        text = """
policy {
  allow database[*]
}
u := source @db "select 1"
        """
        prog = compiler.parse(text)
        res = compiler.compile(prog, "build_test")
        self.assertTrue(os.path.exists("build_test/runtime_generated.py"))
        shutil.rmtree("build_test")

if __name__ == "__main__":
    unittest.main()

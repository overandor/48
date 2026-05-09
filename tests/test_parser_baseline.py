import textwrap

from semantic_protocol_runtime import ProgramParser


def test_parse_hot_users_protocol():
    source = textwrap.dedent(
        '''
        policy {
          optimize: latency > cost
          deterministic: true
          allow database[db.main]
          allow filesystem[*]
          deny network[*]
          deny shell[*]
        }

        users := source @db.main "select id, email, score from users"
        hot   := users -> filter score > 0.8 -> project [id, email, score]
        write! hot @file:"hot_users.jsonl"
        '''
    ).strip()

    program = ProgramParser().parse(source)

    assert program.policy.deterministic is True
    assert len(program.bindings) == 2
    assert len(program.effects) == 1
    assert program.bindings[0].name == "users"
    assert program.bindings[0].source.runtime == "db.main"
    assert program.bindings[1].name == "hot"
    assert [op.name for op in program.bindings[1].ops] == ["filter", "project"]
    assert program.effects[0].effect_name == "write"


def test_parse_type_annotation_and_runtime_hint():
    source = textwrap.dedent(
        '''
        policy {
          deterministic: true
          allow database[db.main]
        }

        users: table[id,email,score] @sql := source @db.main "select id, email, score from users"
        '''
    ).strip()

    program = ProgramParser().parse(source)
    binding = program.bindings[0]

    assert binding.name == "users"
    assert binding.runtime_hint == "sql"
    assert binding.declared_type.base == "table"
    assert [param.base for param in binding.declared_type.params] == ["id", "email", "score"]

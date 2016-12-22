import pytest

from gql import Client
from gql.dsl import DSLSchema

from .schema import StarWarsSchema


@pytest.fixture
def client():
    return Client(schema=StarWarsSchema)


@pytest.fixture
def ds(client):
    ds = DSLSchema(client)
    return ds


def test_hero_name_query(ds):
    query = '''
hero {
  name
}
    '''.strip()
    query_dsl = ds.Query.hero.select(
        ds.Character.name
    )
    assert query == str(query_dsl)


def test_hero_name_and_friends_query(ds):
    query = '''
hero {
  id
  name
  friends {
    name
  }
}
    '''.strip()
    query_dsl = ds.Query.hero.select(
        ds.Character.id,
        ds.Character.name,
        ds.Character.friends.select(
            ds.Character.name,
        )
    )
    assert query == str(query_dsl)


def test_nested_query(ds):
    query = '''
hero {
  name
  friends {
    name
    appearsIn
    friends {
      name
    }
  }
}
    '''.strip()
    query_dsl = ds.Query.hero.select(
        ds.Character.name,
        ds.Character.friends.select(
            ds.Character.name,
            ds.Character.appears_in,
            ds.Character.friends.select(
                ds.Character.name
            )
        )
    )
    assert query == str(query_dsl)


def test_fetch_luke_query(ds):
    query = '''
human(id: "1000") {
  name
}
    '''.strip()
    query_dsl = ds.Query.human(id="1000").select(
        ds.Human.name,
    )

    assert query == str(query_dsl)


# def test_fetch_some_id_query():
#     query = '''
#         query FetchSomeIDQuery($someId: String!) {
#           human(id: $someId) {
#             name
#           }
#         }
#     '''
#     params = {
#         'someId': '1000',
#     }
#     expected = {
#         'human': {
#             'name': 'Luke Skywalker',
#         }
#     }
#     result = schema.execute(query, None, params)
#     assert not result.errors
#     assert result.data == expected


# def test_fetch_some_id_query2():
#     query = '''
#         query FetchSomeIDQuery($someId: String!) {
#           human(id: $someId) {
#             name
#           }
#         }
#     '''
#     params = {
#         'someId': '1002',
#     }
#     expected = {
#         'human': {
#             'name': 'Han Solo',
#         }
#     }
#     result = schema.execute(query, None, params)
#     assert not result.errors
#     assert result.data == expected


# def test_invalid_id_query():
#     query = '''
#         query humanQuery($id: String!) {
#           human(id: $id) {
#             name
#           }
#         }
#     '''
#     params = {
#         'id': 'not a valid id',
#     }
#     expected = {
#         'human': None
#     }
#     result = schema.execute(query, None, params)
#     assert not result.errors
#     assert result.data == expected


def test_fetch_luke_aliased(ds):
    query = '''
luke: human {
  name
}
    '''.strip()
    query_dsl = ds.Query.human.alias('luke').select(
        ds.Character.name,
    )
    assert query == str(query_dsl)


def test_fetch_alias_as_keyword(ds):
    query = '''
human {
  my_name: name
}
    '''.strip()
    query_dsl = ds.Query.human.select(
        my_name=ds.Character.name,
    )
    assert query == str(query_dsl)


# def test_fetch_luke_and_leia_aliased():
#     query = '''
#         query FetchLukeAndLeiaAliased {
#           luke: human(id: "1000") {
#             name
#           }
#           leia: human(id: "1003") {
#             name
#           }
#         }
#     '''
#     expected = {
#         'luke': {
#             'name': 'Luke Skywalker',
#         },
#         'leia': {
#             'name': 'Leia Organa',
#         }
#     }
#     result = schema.execute(query)
#     assert not result.errors
#     assert result.data == expected


# def test_duplicate_fields():
#     query = '''
#         query DuplicateFields {
#           luke: human(id: "1000") {
#             name
#             homePlanet
#           }
#           leia: human(id: "1003") {
#             name
#             homePlanet
#           }
#         }
#     '''
#     expected = {
#         'luke': {
#             'name': 'Luke Skywalker',
#             'homePlanet': 'Tatooine',
#         },
#         'leia': {
#             'name': 'Leia Organa',
#             'homePlanet': 'Alderaan',
#         }
#     }
#     result = schema.execute(query)
#     assert not result.errors
#     assert result.data == expected


# def test_use_fragment():
#     query = '''
#         query UseFragment {
#           luke: human(id: "1000") {
#             ...HumanFragment
#           }
#           leia: human(id: "1003") {
#             ...HumanFragment
#           }
#         }
#         fragment HumanFragment on Human {
#           name
#           homePlanet
#         }
#     '''
#     expected = {
#         'luke': {
#             'name': 'Luke Skywalker',
#             'homePlanet': 'Tatooine',
#         },
#         'leia': {
#             'name': 'Leia Organa',
#             'homePlanet': 'Alderaan',
#         }
#     }
#     result = schema.execute(query)
#     assert not result.errors
#     assert result.data == expected


# def test_check_type_of_r2():
#     query = '''
#         query CheckTypeOfR2 {
#           hero {
#             __typename
#             name
#           }
#         }
#     '''
#     expected = {
#         'hero': {
#             '__typename': 'Droid',
#             'name': 'R2-D2',
#         }
#     }
#     result = schema.execute(query)
#     assert not result.errors
#     assert result.data == expected


# def test_check_type_of_luke():
#     query = '''
#         query CheckTypeOfLuke {
#           hero(episode: EMPIRE) {
#             __typename
#             name
#           }
#         }
#     '''
#     expected = {
#         'hero': {
#             '__typename': 'Human',
#             'name': 'Luke Skywalker',
#         }
#     }
#     result = schema.execute(query)
#     assert not result.errors
#     assert result.data == expected

from datetime import datetime
from pytz import timezone

def test_hero_name_query_basic(ds):
    Query, Character = ds.Query, ds.Character

    result = ds.query(
        Query.hero.select(
            Character.name
        )
    )

    assert isinstance(result, Query)
    assert isinstance(result.hero, Character)
    assert result.hero.name == 'R2-D2'


def test_hero_name_query(ds):
    Query, Character = ds.Query, ds.Character

    my_birthday = datetime(year=1988, month=11, day=7, tzinfo=timezone('UTC'))

    result = ds.query(
        Query.date(date=my_birthday),
    )

    assert isinstance(result.date, datetime)
    assert result.date == my_birthday

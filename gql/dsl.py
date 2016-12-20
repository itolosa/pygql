import collections
import decimal
from functools import partial

import six
from graphql.language import ast
from graphql.language.printer import print_ast
from graphql.type import (GraphQLField, GraphQLList,
                          GraphQLNonNull, GraphQLEnumType,
                          GraphQLObjectType, GraphQLInterfaceType,
                          GraphQLUnionType)

from .utils import to_camel_case


class DSLSchema(object):
    def __init__(self, client):
        self.client = client

    @property
    def schema(self):
        return self.client.schema

    def __getattr__(self, name):
        type_def = self.schema.get_type(name)
        return DSLType(type_def)

    def query(self, *args, **kwargs):
        return self.execute(query(*args, **kwargs))

    def mutate(self, *args, **kwargs):
        return self.query(*args, operation='mutate', **kwargs)

    def execute(self, document):
        return self.client.execute(document)


class DSLType(object):
    def __init__(self, type):
        self.type = type

    def __getattr__(self, name):
        formatted_name, field_def = self.get_field(name)
        return DSLField(formatted_name, field_def)

    def get_field(self, name):
        camel_cased_name = to_camel_case(name)

        if name in self.type.fields:
            return name, self.type.fields[name]

        if camel_cased_name in self.type.fields:
            return camel_cased_name, self.type.fields[camel_cased_name]

        raise KeyError('Field {} doesnt exist in type {}.'.format(name, self.type.name))


def get_ast_value(value):
    if isinstance(value, ast.Node):
        return value
    if isinstance(value, six.string_types):
        return ast.StringValue(value=value)
    elif isinstance(value, bool):
        return ast.BooleanValue(value=value)
    elif isinstance(value, (float, decimal.Decimal)):
        return ast.FloatValue(value=value)
    elif isinstance(value, int):
        return ast.IntValue(value=value)
    return None

_TYPENAME = ast.Field(name=ast.Name(value='__typename'))

class DSLField(object):

    def __init__(self, name, field):
        self.name = name
        self.field = field
        self.base_type = get_base_type(field.type)
        self.selections = []
        self._args = {}
        self._as = None

    def select(self, *fields):
        self.selections.extend(fields)
        return self

    def __call__(self, *args, **kwargs):
        return self.args(*args, **kwargs)

    def alias(self, alias):
        self._as = alias
        return self

    def args(self, **args):
        self._args.update(args)
        return self

    def ast(self, with_typename=False):
        
        alias = self._as and ast.Name(value=self._as)
        arguments = []
        selection_set = None
        if isinstance(self.base_type, (GraphQLObjectType, GraphQLInterfaceType)):
            selections = [field.ast(with_typename) for field in self.selections]
            if with_typename:
                selections = [_TYPENAME] + selections
            selection_set = ast.SelectionSet(
                selections=selections
            )

        for name, value in self._args.items():
            arg = self.field.args.get(name)
            arg_type_serializer = get_arg_serializer(arg.type)
            value = arg_type_serializer(value)
            arguments.append(
                ast.Argument(
                    name=ast.Name(value=name),
                    value=get_ast_value(value)
                )
            )

        ast_field = ast.Field(
            name=ast.Name(value=self.name),
            arguments=arguments,
            alias=alias,
            selection_set=selection_set
        )

        return ast_field

    def __str__(self):
        return print_ast(self.ast())


def query(*fields):
    return ast.Document(
        definitions=[ast.OperationDefinition(
            operation='query',
            selection_set=ast.SelectionSet(
                selections=[field.ast(True) for field in fields]
            )
        )]
    )


def serialize_list(serializer, values):
    assert isinstance(values, collections.Iterable), 'Expected iterable, received "{}"'.format(repr(values))
    return [serializer(v) for v in values]


def get_arg_serializer(arg_type):
    if isinstance(arg_type, GraphQLNonNull):
        return get_arg_serializer(arg_type.of_type)
    if isinstance(arg_type, GraphQLList):
        inner_serializer = get_arg_serializer(arg_type.of_type)
        return partial(serialize_list, inner_serializer)
    if isinstance(arg_type, GraphQLEnumType):
        return lambda value: ast.EnumValue(value=arg_type.serialize(value))
    return arg_type.serialize


def get_base_type(type):
    if isinstance(type, (GraphQLList, GraphQLNonNull)):
        return get_base_type(type.of_type)
    return type


def var(name):
    return ast.Variable(name=name)

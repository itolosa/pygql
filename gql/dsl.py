import copy

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

from .utils import to_snake_case


class DSLSchema(object):
    def __init__(self, client):
        self.client = client
        self._cached_types = {}
        self.query = DSLOperation(self.schema.get_query_type(), self)

    @property
    def schema(self):
        return self.client.schema

    def __getattr__(self, name):
        if name not in self._cached_types:
            type_def = self.schema.get_type(name)
            self._cached_types[name] = self._convert_type_def_to_class(type_def)
        return self._cached_types[name]

    def _convert_type_def_to_class(self, type_def, auto_snake_case=True):
        fields = {}
        for name, field_def in type_def.fields.items():
            if auto_snake_case:
                attr_name = to_snake_case(name)
            else:
                attr_name = name
            fields[attr_name] = DSLField(name, field_def, self)

        return type(str(type_def.name), (object,), fields)

    # def query(self, *args, **kwargs):
    #     return self.execute(query(*args, **kwargs))

    # def mutate(self, *args, **kwargs):
    #     return self.query(*args, operation='mutate', **kwargs)

    def execute(self, document):
        return self.client.execute(document)


# class DSLType(object):
#     def __init__(self, type):
#         self.type = type

#     def __getattr__(self, name):
#         formatted_name, field_def = self.get_field(name)
#         return DSLField(formatted_name, field_def)

    # def get_field(self, name):
    #     camel_cased_name = to_camel_case(name)

    #     if name in self.type.fields:
    #         return name, self.type.fields[name]

    #     if camel_cased_name in self.type.fields:
    #         return camel_cased_name, self.type.fields[camel_cased_name]

    #     raise KeyError('Field {} doesnt exist in type {}.'.format(name, self.type.name))


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


def fragment(operation_or_field):
    _type = operation_or_field.type
    selections = operation_or_field.selections
    dsl_type = operation_or_field.dsl_type

    fragment_basetype = collections.namedtuple(
        _type.name,
        [f.attr for f in selections]
    )
    return type(_type.name, (fragment_basetype, dsl_type), {'_dsl_type': dsl_type})


class DSLOperation(object):

    def __init__(self, type, dsl):
        self.dsl = dsl
        self.selections = []
        self.type = type
        self.dsl_type = getattr(self.dsl, self.type.name)
        self.operation = 'query'

    def select(self, *fields):
        self.selections.extend(fields)
        return self

    def __call__(self, *fields):
        return self.select(*fields)

    @property
    def fragment(self):
        return fragment(self)

    def ast(self, with_typename=False):
        selections = [field.ast(with_typename) for field in self.selections]

        if with_typename:
            selections = [_TYPENAME] + selections

        return ast.Document(
            definitions=[ast.OperationDefinition(
                operation=self.operation,
                selection_set=ast.SelectionSet(
                    selections=selections
                )
            )]
        )

    def inflate(self, value):
        assert isinstance(value, dict)

        kwargs = {}
        for selection in self.selections:
            attr = selection.attr
            kwargs[attr] = selection.inflate(value.get(attr))

        return self.fragment(**kwargs)

    def execute(self, *args, **kwargs):
        ast = self.ast()
        result = self.dsl.execute(ast, *args, **kwargs)
        return self.inflate(result)


class DSLField(object):

    def __init__(self, name=None, field=None, dsl=None):
        self.dsl = dsl
        self.name = name
        self.field = field
        self.type = get_base_type(field.type)
        self.selections = []
        self._args = {}
        self._as = None

    def select(self, *fields):
        instance = self._clone()
        instance.selections.extend(fields)
        return instance

    def __call__(self, *args, **kwargs):
        return self.args(*args, **kwargs)

    @property
    def attr(self):
        return self._as or self.name

    def alias(self, alias):
        instance = self._clone()
        instance._as = alias
        return instance

    def args(self, **args):
        instance = self._clone()
        instance._args.update(args)
        return instance

    def inflate(self, value):
        if not self.has_selections:
            return value

        assert isinstance(value, dict)

        kwargs = {}
        for selection in self.selections:
            attr = selection.attr
            kwargs[attr] = selection.inflate(value.get(attr))

        return self.fragment(**kwargs)

    @property
    def has_selections(self):
        return isinstance(self.type, (GraphQLObjectType, GraphQLInterfaceType))

    @property
    def dsl_type(self):
        if not self.has_selections:
            return
        return getattr(self.dsl, self.type.name)

    @property
    def fragment(self):
        return fragment(self)

    def ast(self, with_typename=False):
        
        alias = self._as and ast.Name(value=self._as)
        arguments = []
        selection_set = None
        if self.has_selections:
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


    def _clone(self):
        instance = DSLField(
            self.name,
            self.field,
            self.dsl
        )
        instance.selections = copy.deepcopy(self.selections)
        instance._args = copy.copy(self._args)
        instance._as = copy.copy(self._as)
        return instance


def query(*fields):
    return ast.Document(
        definitions=[ast.OperationDefinition(
            operation='query',
            selection_set=ast.SelectionSet(
                selections=[_TYPENAME] + [field.ast(True) for field in fields]
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

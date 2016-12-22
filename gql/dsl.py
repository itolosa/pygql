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

            field_base_type = get_base_type(field_def.type)
            # print isinstance(field_base_type, (GraphQLObjectType, GraphQLInterfaceType)), field_base_type
            if isinstance(field_base_type, (GraphQLObjectType, GraphQLInterfaceType)):
                dsl_field = DSLSelectionField(name, field_base_type, field_def, self, attr_name)
            else:
                dsl_field = DSLField(name, field_base_type, field_def, self, attr_name)
            fields[attr_name] = dsl_field

        return type(str(type_def.name), (object,), fields)

    def execute(self, document):
        return self.client.execute(document)


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



class DSLSelection(object):

    def __init__(self, *args, **kwargs):
        self.selections = []
        super(DSLSelection, self).__init__(*args, **kwargs)


    def select(self, *fields, **fields_with_alias):
        instance = self._clone()
        instance.selections.extend(fields)
        for alias, field in fields_with_alias.items():
            instance.selections.append(
                field.alias(alias)
            )
        return instance

    def inflate(self, value):
        assert isinstance(value, dict)

        kwargs = {}
        for selection in self.selections:
            attr = selection.attr
            kwargs[selection.attrn] = selection.inflate(value.get(attr))

        return self.fragment(**kwargs)

    @property
    def fragment(self):
        dsl_type = self.dsl_type
        type_name = str(self.type.name)
        # We create a type with the fields same as the selections
        fragment_basetype = collections.namedtuple(
            type_name,
            [f.attrn for f in self.selections]
        )
        # We construct a type which inherits the dsl_type (so we can do isinstance(x, dsl_type))
        # And the created fragment type
        return type(type_name, (fragment_basetype, dsl_type), {'_dsl_type': dsl_type})

    @property
    def ast_selection(self):
        return ast.SelectionSet(
            selections=[field.ast for field in self.selections]
        )


class DSLOperation(DSLSelection):

    def __init__(self, type, dsl):
        self.dsl = dsl
        self.selections = []
        self.type = type
        self.dsl_type = getattr(self.dsl, self.type.name)
        self.operation = 'query'
        super(DSLOperation, self).__init__()

    def __call__(self, *fields, **kwargs):
        return self.select(*fields).execute(**kwargs)

    @property
    def ast(self):
        return ast.Document(
            definitions=[ast.OperationDefinition(
                operation=self.operation,
                selection_set=self.ast_selection
            )]
        )

    def execute(self, *args, **kwargs):
        ast = self.ast
        result = self.dsl.execute(ast, *args, **kwargs)
        return self.inflate(result)

    def _clone(self):
        instance = DSLOperation(
            self.type,
            self.dsl
        )
        instance.selections = copy.deepcopy(self.selections)
        return instance


class DSLField(object):

    def __init__(self, name=None, type=None, field=None, dsl=None, attr_name=None):
        self.dsl = dsl
        self.name = name
        self.field = field
        self.type = type
        self.attr_name = attr_name
        self._args = {}
        self._as = None
        super(DSLField, self).__init__()

    def __call__(self, *args, **kwargs):
        return self.args(*args, **kwargs)

    def inflate(self, value):
        return value

    @property
    def attr(self):
        return self._as or self.name

    @property
    def attrn(self):
        return self._as or self.attr_name

    def alias(self, alias):
        instance = self._clone()
        instance._as = alias
        return instance

    def args(self, **args):
        instance = self._clone()
        instance._args.update(args)
        return instance

    @property
    def ast(self):
        alias = self._as and ast.Name(value=self._as)
        arguments = []

        for name, value in self._args.items():
            arg = self.field.args.get(name)
            arg_type_serializer = get_serializer(arg.type)
            value = arg_type_serializer(value)
            arguments.append(
                ast.Argument(
                    name=ast.Name(value=name),
                    value=get_ast_value(value)
                )
            )

        return ast.Field(
            name=ast.Name(value=self.name),
            arguments=arguments,
            alias=alias,
        )

    def __str__(self):
        return print_ast(self.ast)

    def _clone(self):
        instance = self.__class__(
            self.name,
            self.type,
            self.field,
            self.dsl,
            self.attr_name
        )
        instance._args = copy.copy(self._args)
        instance._as = copy.copy(self._as)
        return instance


class DSLSelectionField(DSLSelection, DSLField):
    @property
    def dsl_type(self):
        return getattr(self.dsl, self.type.name)

    @property
    def ast(self):
        ast_field = super(DSLSelectionField, self).ast
        ast_field.selection_set = self.ast_selection
        return ast_field

    def _clone(self):
        instance = super(DSLSelectionField, self)._clone()
        instance.selections = copy.deepcopy(self.selections)
        return instance


def serialize_list(serializer, values):
    assert isinstance(values, collections.Iterable), 'Expected iterable, received "{}"'.format(repr(values))
    return [serializer(v) for v in values]


def get_serializer(_type):
    if isinstance(_type, GraphQLNonNull):
        return get_serializer(_type.of_type)
    if isinstance(_type, GraphQLList):
        inner_serializer = get_serializer(_type.of_type)
        return partial(serialize_list, inner_serializer)
    if isinstance(_type, GraphQLEnumType):
        return lambda value: ast.EnumValue(value=_type.serialize(value))
    return _type.serialize


def get_parse_value(_type):
    if isinstance(_type, GraphQLNonNull):
        return get_parse_value(_type.of_type)
    if isinstance(_type, GraphQLList):
        inner_serializer = get_parse_value(_type.of_type)
        return partial(serialize_list, inner_serializer)
    if isinstance(_type, GraphQLEnumType):
        return lambda value: ast.EnumValue(value=_type.parse_value(value))
    return _type.parse_value


def get_base_type(type):
    if isinstance(type, (GraphQLList, GraphQLNonNull)):
        return get_base_type(type.of_type)
    return type


def var(name):
    return ast.Variable(name=name)

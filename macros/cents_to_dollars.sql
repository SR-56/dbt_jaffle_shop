{# セント単位の整数をドル単位の decimal に直す。DuckDB では decimal / 100 が double になるので、割ったあとにキャストする #}
{% macro cents_to_dollars(column_name) -%}
    cast({{ column_name }} / 100 as decimal(16, 2))
{%- endmacro %}

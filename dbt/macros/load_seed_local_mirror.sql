{#
    Override of the_tuva_project's DuckDB seed loader.

    Default behavior is unchanged: read from S3 with DuckDB's httpfs extension.
    If the var `tuva_seed_mirror` is set (a folder made by
    scripts/mirror_tuva_seeds.py), read the same files from local disk instead,
    so no httpfs extension or S3 access is needed at build time.
#}
{% macro duckdb__load_seed(uri, pattern, compression, headers, null_marker) %}
{%- set mirror = var('tuva_seed_mirror', none) -%}
{%- if mirror is none -%}
  {{ return(the_tuva_project.duckdb__load_seed(uri, pattern, compression, headers, null_marker)) }}
{%- endif -%}

{%- set columns = adapter.get_columns_in_relation(this) -%}
{%- set collist = [] -%}
{%- for col in columns -%}
  {%- do collist.append("'" ~ col.name ~ "': '" ~ col.dtype ~ "'") -%}
{%- endfor -%}
{%- set path = mirror ~ '/' ~ uri ~ '/' ~ pattern ~ '*' -%}

{% set sql %}
  create or replace table {{ this }} as
  select *
  from read_csv('{{ path }}',
      {% if null_marker == true %} nullstr = ['', '\N'] {% else %} nullstr = '' {% endif %},
      quote = '"', escape = '"',
      header = {{ headers }},
      columns = { {{ collist | join(',') }} })
{% endset %}

{% call statement('ducksql', fetch_result=true) %}{{ sql }}{% endcall %}
{% if execute %}
  {{ log("Loaded " ~ this ~ " from local mirror " ~ path, info=true) }}
{% endif %}
{% endmacro %}

"""Fabrication guard: flags tools, numbers, and certifications in generated text that aren't in the master profile.

This is a safety net, not a proof: it catches the common failure modes (invented tools, invented
metrics, in-progress certs stated as earned). Findings trigger a regeneration and, if they persist,
are saved to applications.validation_warnings and shown on the dashboard.
"""
from __future__ import annotations

import re

# Ambiguous English words (Go, R, Mode, Segment, Glue...) are deliberately left out.
# Tools/tech commonly found in data & infra JDs. Anything here that appears in output but not in the
# profile is flagged. Extend as you see new false negatives.
TECH_LEXICON = [
    "Snowflake", "BigQuery", "Redshift", "Databricks", "Spark", "Kafka", "Flink", "Hadoop", "Hive",
    "Presto", "Trino", "Athena", "EMR", "Kinesis", "S3", "Dataflow", "Dataproc", "Pub/Sub",
    "Looker", "Tableau", "Qlik", "Metabase", "Superset", "ThoughtSpot",
    "Fivetran", "Matillion", "Informatica", "Talend", "SSIS", "Dagster", "Prefect", "Luigi",
    "Great Expectations", "Monte Carlo", "Collibra", "Alation", "Purview", "Unity Catalog",
    "Iceberg", "Hudi", "Parquet", "Avro", "Cassandra", "DynamoDB", "Redis", "Elasticsearch", "Neo4j",
    "Oracle", "Teradata", "Vertica", "ClickHouse", "DuckDB", "Pinot", "Druid",
    "Scala", "Java", "Golang", "Rust", "Julia", "TypeScript", "JavaScript", "C#", "C\\+\\+",
    "TensorFlow", "PyTorch", "scikit-learn", "XGBoost", "MLflow", "Kubeflow", "SageMaker", "Vertex AI",
    "LangChain", "LLM", "Pulumi", "CloudFormation", "Helm", "ArgoCD", "Prometheus", "Datadog",
    "Splunk", "New Relic", "CircleCI", "GitLab", "Bitbucket", "Jira", "Confluence",
    "GCP", "Google Cloud", "Six Sigma", "Salesforce", "HubSpot", "Amplitude", "Mixpanel",
    "Airflow", "Airbyte", "dbt", "Pandas", "PySpark", "Kubernetes", "Docker", "Terraform", "Ansible",
    "Jenkins", "Grafana", "Selenium", "Gradle", "Power BI", "Power Automate", "KQL", "DAX", "GraphQL",
    "Delta Lake", "Synapse", "Data Factory", "Azure Monitor", "MongoDB", "PostgreSQL", "MySQL", "SQL Server",
    "SAP", "Excel", "Jupyter", "Bash", "AWS", "Azure", "Microsoft Fabric",
]

IN_PROGRESS_CERTS = [r"GCP|Google Cloud(?: Platform)?(?: Professional)?(?: Data Engineer)?", r"Six Sigma"]
_IN_PROGRESS_QUALIFIER = re.compile(r"pursuing|in progress|working toward|currently (?:studying|preparing)|preparing for", re.I)

_NUMBER = re.compile(r"(?<![\w.])\d+(?:[.,]\d+)?\s*(?:%|[kKmM]\b|\+)?")


def _norm_num(s: str) -> str:
    return re.sub(r"\s+|,", "", s).lower().rstrip("+")


def _mentions(term: str, text: str) -> bool:
    return re.search(rf"(?<![\w-]){term}(?![\w-])", text, re.I) is not None


def check_text(text: str, profile_md: str, *, allowed_numbers: set[str] = frozenset(),
               extra_context: str = "") -> list[str]:
    """Return human-readable violations found in `text`.

    extra_context: the JD. Tools that appear in it are still flagged (we can't reliably tell
    "I used X" from "your X stack"), but the message says so to speed up review.
    """
    issues = []
    profile_nums = {_norm_num(n) for n in _NUMBER.findall(profile_md)} | {_norm_num(n) for n in allowed_numbers}
    for n in _NUMBER.findall(text):
        if _norm_num(n) not in profile_nums:
            issues.append(f"number '{n.strip()}' not found in master profile")

    for term in TECH_LEXICON:
        if _mentions(term, text) and not _mentions(term, profile_md):
            where = " (appears in JD; make sure it's not claimed as experience)" if _mentions(term, extra_context) else ""
            issues.append(f"tool/tech '{term.replace(chr(92), '')}' not in master profile{where}")

    for cert in IN_PROGRESS_CERTS:
        for m in re.finditer(cert, text, re.I):
            window = text[max(0, m.start() - 80): m.end() + 80]
            if not _IN_PROGRESS_QUALIFIER.search(window):
                issues.append(f"'{m.group(0)}' mentioned without an in-progress qualifier")
    return sorted(set(issues))


def sentence_count(text: str) -> int:
    return len([s for s in re.split(r"(?<=[.!?])\s+", text.strip()) if s])

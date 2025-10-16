from __future__ import annotations

import numpy as np

from pdf2sqlite.embeddings import (
    clean_text,
    extract_keywords,
    generate_topic_name,
    cluster_texts,
)


def test_clean_text_normalizes_whitespace_and_punctuation():
    messy_text = "  Hello,\nWorld!! $ $ 42\t"

    result = clean_text(messy_text)

    assert result.startswith("Hello, World!!")
    assert result.endswith("42")
    assert "\n" not in result
    assert "\t" not in result
    assert "$" not in result


def test_extract_keywords_filters_stop_words():
    text = "alpha alpha beta gamma gamma gamma the and to"

    keywords = extract_keywords(text, max_keywords=3)

    assert keywords == ["gamma", "alpha", "beta"]


def test_generate_topic_name_prefers_frequent_keywords():
    texts = [
        "engine turbine airflow cooling system efficiency",
        "engine turbine airflow metrics",
    ]

    topic_name = generate_topic_name(texts)

    assert topic_name == "Engine & Turbine - Airflow"


def test_cluster_texts_handles_single_sample():
    embeddings = [np.array([0.0, 0.0], dtype=np.float32)]
    texts = ["lorem ipsum"]

    labels, info = cluster_texts(embeddings, texts, n_clusters=3)

    assert labels == [0]
    assert info == {0: {"size": 1, "name": "All Content"}}


def test_cluster_texts_limits_clusters_to_sample_count():
    embeddings = [
        np.array([0.0, 0.0], dtype=np.float32),
        np.array([10.0, 10.0], dtype=np.float32),
    ]
    texts = [
        "alpha beta gamma",
        "delta epsilon zeta",
    ]

    labels, info = cluster_texts(embeddings, texts, n_clusters=5)

    assert sorted(set(labels)) == [0, 1]
    assert set(info.keys()) == {0, 1}
    assert all(details["size"] == 1 for details in info.values())

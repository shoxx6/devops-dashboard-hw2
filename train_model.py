"""Train a small SMS spam Naive Bayes model from the UCI corpus."""

import json
import math
import random
import re
import zipfile
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DATA_PATH = ROOT / "data" / "SMSSpamCollection"
MODEL_DIR = ROOT / "models"
TOKEN_RE = re.compile(r"[a-z0-9]+", re.IGNORECASE)
LABELS = ("ham", "spam")
ALPHA = 1.0


def tokenize(text):
    return TOKEN_RE.findall(text.lower())


def load_messages():
    messages = []
    if DATA_PATH.exists():
        stream_context = DATA_PATH.open(encoding="utf-8", errors="replace")
    else:
        archive = zipfile.ZipFile(ROOT / "data" / "sms-spam-collection.zip")
        stream_context = archive.open("SMSSpamCollection")
    with stream_context as stream:
        for line in stream:
            if isinstance(line, bytes):
                line = line.decode("utf-8", errors="replace")
            label, separator, text = line.rstrip("\n").partition("\t")
            if separator and label in LABELS and text.strip():
                messages.append({"label": label, "text": text})
    if not DATA_PATH.exists():
        archive.close()
    if not messages:
        raise RuntimeError(f"No labeled messages found in {DATA_PATH}")
    return messages


def split_stratified(messages, test_fraction=0.2, seed=42):
    groups = defaultdict(list)
    for item in messages:
        groups[item["label"]].append(item)
    rng = random.Random(seed)
    training, testing = [], []
    for label in LABELS:
        group = groups[label]
        rng.shuffle(group)
        test_count = max(1, round(len(group) * test_fraction))
        testing.extend(group[:test_count])
        training.extend(group[test_count:])
    rng.shuffle(training)
    rng.shuffle(testing)
    return training, testing


def fit(messages):
    document_counts = Counter()
    token_counts = {label: Counter() for label in LABELS}
    token_totals = Counter()
    vocabulary = set()

    for item in messages:
        label = item["label"]
        tokens = tokenize(item["text"])
        document_counts[label] += 1
        token_counts[label].update(tokens)
        token_totals[label] += len(tokens)
        vocabulary.update(tokens)

    return {
        "model_type": "Multinomial Naive Bayes",
        "alpha": ALPHA,
        "vocabulary_size": len(vocabulary),
        "document_counts": dict(document_counts),
        "token_totals": dict(token_totals),
        "token_counts": {label: dict(token_counts[label]) for label in LABELS},
    }


def predict(model, text):
    tokens = tokenize(text)
    document_total = sum(model["document_counts"].values())
    vocabulary_size = model["vocabulary_size"]
    scores = {}
    for label in LABELS:
        prior = model["document_counts"][label] / document_total
        denominator = model["token_totals"][label] + model["alpha"] * vocabulary_size
        score = math.log(prior)
        counts = model["token_counts"][label]
        for token in tokens:
            score += math.log((counts.get(token, 0) + model["alpha"]) / denominator)
        scores[label] = score

    maximum = max(scores.values())
    probabilities = {label: math.exp(value - maximum) for label, value in scores.items()}
    normalizer = sum(probabilities.values())
    probabilities = {label: value / normalizer for label, value in probabilities.items()}
    label = max(probabilities, key=probabilities.get)
    return label, probabilities


def evaluate(model, messages):
    confusion = {label: {other: 0 for other in LABELS} for label in LABELS}
    for item in messages:
        predicted, _ = predict(model, item["text"])
        confusion[item["label"]][predicted] += 1

    true_spam = confusion["spam"]["spam"]
    false_spam = confusion["ham"]["spam"]
    missed_spam = confusion["spam"]["ham"]
    total_correct = confusion["ham"]["ham"] + true_spam
    precision = true_spam / (true_spam + false_spam) if true_spam + false_spam else 0.0
    recall = true_spam / (true_spam + missed_spam) if true_spam + missed_spam else 0.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    return {
        "accuracy": total_correct / len(messages),
        "precision_spam": precision,
        "recall_spam": recall,
        "f1_spam": f1,
        "test_samples": len(messages),
        "training_samples": sum(model["document_counts"].values()),
        "confusion": confusion,
    }


def main():
    messages = load_messages()
    training, testing = split_stratified(messages)
    model = fit(training)
    metrics = evaluate(model, testing)
    MODEL_DIR.mkdir(parents=True, exist_ok=True)
    (MODEL_DIR / "sms_spam_model.json").write_text(
        json.dumps(model, ensure_ascii=False, separators=(",", ":")), encoding="utf-8"
    )
    (MODEL_DIR / "metrics.json").write_text(
        json.dumps(metrics, indent=2), encoding="utf-8"
    )
    print(
        f"Trained on {metrics['training_samples']} messages; "
        f"held-out accuracy {metrics['accuracy']:.3f}; spam F1 {metrics['f1_spam']:.3f}; "
        f"vocabulary {model['vocabulary_size']} tokens."
    )


if __name__ == "__main__":
    main()

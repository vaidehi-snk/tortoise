"""HotpotQA's official answer scoring (exact match and token F1). Pure code, no IO."""
import re
import string
from collections import Counter

_PUNCT = set(string.punctuation)


def normalize(s: str) -> str:
    s = (s or "").lower()
    s = "".join(ch for ch in s if ch not in _PUNCT)
    s = re.sub(r"\b(a|an|the)\b", " ", s)
    return " ".join(s.split())


def exact_match(pred: str, gold: str) -> float:
    return float(normalize(pred) == normalize(gold))


def f1(pred: str, gold: str) -> float:
    p, g = normalize(pred), normalize(gold)
    special = {"yes", "no", "noanswer"}
    if (p in special or g in special) and p != g:
        return 0.0
    pt, gt = p.split(), g.split()
    common = Counter(pt) & Counter(gt)
    same = sum(common.values())
    if same == 0:
        return 0.0
    precision, recall = same / len(pt), same / len(gt)
    return 2 * precision * recall / (precision + recall)

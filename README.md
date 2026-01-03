# Discord ML Moderation Bot

> A context-aware Discord moderation bot that detects spam and advertisements using rules, similarity, and lightweight machine learning.

## 1. Project Motivation

Spam and advertisement accounts on Discord servers often follow predictable behavioral and linguistic patterns:

* They are newly created or newly joined accounts
* They frequently post advertisements as their *first message*
* Messages tend to follow repetitive templates (ticket sales, electronics, crypto, etc.)

This project aims to build a **context-aware, machine-learning–assisted moderation bot** that detects and mitigates spam while minimizing false positives and moderator overhead.

The key challenge addressed is **data scarcity**: spam events are relatively rare, but highly structured.

---

## 2. Goals

### Core Goals

* Monitor early user activity (first 1–3 messages)
* Automatically detect spam and advertisements
* Take low-risk moderation actions (delete, log, escalate)
* Operate effectively with minimal labeled data

### Non-Goals (Initial Version)

* Full conversational moderation
* Toxicity or hate-speech detection
* Automatic permanent bans without review

---

## 3. Design Philosophy

This project intentionally uses a **hybrid system**:

* **Rules** for high-precision detection of obvious spam
* **Similarity & anomaly detection** to leverage repeated templates
* **Lightweight ML models** trained using weak supervision

ML is used to *refine decisions*, not replace deterministic signals.

---

## 4. System Architecture

```
Discord Gateway
      |
      v
Message Listener (Bot)
      |
      v
Feature Extraction
      |
      v
Decision Pipeline
  ├─ Rule-based checks
  ├─ Template similarity
  └─ ML classifier (later)
      |
      v
Moderation Action + Logging
```

---

## 5. Signals Used

### User Context Signals

* Account age
* Server join age
* Message count
* Role assignment

### Message Signals

* First-message flag
* URL / invite count
* Message length
* Keyword presence
* Template similarity

---

## 6. Data Strategy

### Logging First

All early messages are logged *before* aggressive enforcement.

### Weak Supervision

Labels are generated using:

* High-confidence rules (spam)
* Trusted users (normal)
* Manual review of edge cases

### Template Reuse

Repeated spam messages are detected using embedding similarity, allowing one labeled example to generalize across many attacks.

---

## 7. Moderation Policy (Initial)

| Confidence | Action         |
| ---------- | -------------- |
| Low        | Log only       |
| Medium     | Delete message |
| High       | Timeout user   |

No automatic permanent bans in v1.

---

## 8. Evaluation

Success is measured by:

* Precision on first-message spam
* Moderator review burden
* False-positive rate on new users

---

## 9. Roadmap

### Phase 1

* Logging + rule-based deletion

### Phase 2

* Template similarity detection

### Phase 3

* Weakly supervised ML classifier

### Phase 4

* Active learning + moderator feedback

---

## 10. Ethical Considerations

* Conservative enforcement thresholds
* Transparent logging
* Human override capability
* Avoidance of demographic or identity-based features

---

## 11. Tech Stack (Initial)

* Python
* discord.py
* scikit-learn
* sentence-transformers

---

## 12. Status

Current Phase: **Day 1 – Logging & Infrastructure**

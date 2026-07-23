# Maya AI — Custom Model Training Plan

**Goal:** Train a custom Bengali-first, multilingual conversational model for Maya AI

**Languages:** Bengali (Banglish), Hindi (Hindlish), English, Mixed code-switching

**Budget:** $0 (Student-Friendly, 100% Free)

**Target Model:** Qwen2.5-1.5B-Instruct + LoRA/QLoRA

**Last Updated:** 2026-07-22

---

## 1. Why Build a Custom Model?

Maya currently depends on external APIs (Gemini, OpenAI, etc.) for all LLM reasoning. This means:

- Internet is mandatory
- API costs accumulate
- No offline capability
- No Bengali-native understanding
- Provider downtime kills the assistant

A custom model fixes all of this:

- Fully offline capable
- Zero API costs after training
- Native Bengali/Hindi/Banglish understanding
- Runs on any hardware (even CPU)
- No provider dependency

---

## 2. Target Model Selection

### Why Qwen2.5-1.5B-Instruct?

| Factor | Reason |
|---|---|
| Size | 1.5B params — fits Colab free T4 GPU (15GB) easily |
| Bengali support | Strong multilingual including Bengali |
| Instruct-tuned | Already good at following instructions |
| License | Apache 2.0 — free for commercial use |
| Ollama support | One-click local deployment |
| Community | Active, well-documented |

### Alternative Models

| Model | Size | Bengali | Colab Free | Notes |
|---|---|---|---|---|
| Qwen2.5-1.5B-Instruct | 1.5B | Strong | Yes | Primary choice |
| Gemma2-2B | 2B | Good | Tight fit | Google model |
| LLaMA3.2-3B | 3B | Limited | No | Too big for free Colab |
| Phi-3-mini-4k | 3.8B | Limited | No | English-focused |
| SmolLM2-1.7B | 1.7B | Weak | Yes | Bengali weak |

**Winner: Qwen2.5-1.5B-Instruct**

---

## 3. Languages and Conversational Styles

Maya must handle four distinct conversational styles:

### 3.1 Bengali (Banglish) — Romanized Bengali

```json
{"user": "ami valo nai, kemon acho?", "assistant": "Ami bhalo achi! Tumi ki korchho ekhon?"}
{"user": "ajker weather ki?", "assistant": "Ami weather check korte parbo na. Tumi ki chaile internet e dekhte paro."}
{"user": "tumi ki bhalo model?", "assistant": "Ami learn korchi! Tumi jodi help koro, ami aro bhalo hote pari."}
```

**Common Banglish Words:**

- ami = I/me
- tumi = you
- apni = you (respectful)
- valo/bhalo = good
- kemon = how
- korchho = doing
- ache = is/are
- nai = no/not
- ha = yes
- dhonnobad = thank you
- ashche = coming
- jabo = will go
- kotha = talk/speech
- jan = know

### 3.2 Hindi (Hindlish) — Romanized Hindi

```json
{"user": "tum kaise ho?", "assistant": "Main theek hoon! Tum kya kar rahe ho abhi?"}
{"user": "volume badhao", "assistant": "Volume badha diya. Aur kuch chahiye?"}
{"user": "mujhe help chahiye", "assistant": "Bilkul! Batao kya karna hai, main help karunga."}
```

**Common Hindlish Words:**

- main = I/me
- tum = you (informal)
- aap = you (respectful)
- accha = good
- kaise = how
- kar rahe = doing
- hai = is/are
- nahi = no/not
- haan = yes
- shukriya = thank you
- aa raha = coming
- jaunga = will go
- baat = talk/speech
- jaanta = know

### 3.3 English

```json
{"user": "how are you?", "assistant": "I'm doing great! What are you working on?"}
{"user": "open notepad", "assistant": "Opening Notepad. Anything else you need?"}
{"user": "help me with code", "assistant": "Sure! What language and what do you need?"}
```

### 3.4 Mixed Code-Switching (Real World)

Users naturally mix languages. The model must handle this:

```json
{"user": "bhai volume thoda kam karo", "assistant": "Volume kam kar diya. Aur kuch?"}
{"user": "ami tired but kaaj ache", "assistant": "Rest korte paro, kaaj poreo hobe."}
{"user": "dost ke bhejo message", "assistant": "Kaunsa message bhejna hai, aur kisko?"}
{"user": "ami kal exam ache, help koro please", "assistant": "Bhalo! Ki subject? Ami help korbo."}
{"user": "yaar ye laptop kitna slow hai", "assistant": "Slow? Ami check korbo. Tumi ki chaile cleanup korte pari."}
```

---

## 4. Data Collection Strategy

### 4.1 Primary Source: Gemini AI Studio (FREE)

**Step 1:** Go to https://aistudio.google.com/

**Step 2:** Get free API key (Google account required)

**Step 3:** Generate data using this master prompt:

```
You are a data generator for a Bengali-first AI assistant called Maya.

Generate 50 conversational Q&A pairs in the specified language style.
Each pair must be realistic, natural, and varied.

Language style: {BANGLISH / HINDLISH / ENGLISH / MIXED}

Rules:
1. Use ONLY the specified language style
2. Include system control commands (volume, brightness, open app, etc.)
3. Include casual conversation (greetings, feelings, daily life)
4. Include coding/technical questions
5. Include Bengali/Hindi cultural references
6. Include friendship and emotional support conversations
7. Include weather, time, reminder queries
8. Each response should be 1-3 sentences, natural and helpful
9. Include "I don't know" style responses for things Maya cannot do
10. Never respond in Bengali/Devanagari script — always Roman letters

Format: JSON array of objects with "user" and "assistant" keys.
```

### 4.2 Batch Generation Strategy

| Batch | Topic | Language | Count |
|---|---|---|---|
| 1-5 | Casual conversation | Banglish | 250 |
| 6-10 | System control | Banglish | 250 |
| 11-15 | Coding help | Banglish | 250 |
| 16-20 | Emotional support | Banglish | 250 |
| 21-25 | Casual conversation | Hindlish | 250 |
| 26-30 | System control | Hindlish | 250 |
| 31-35 | Casual conversation | English | 250 |
| 36-40 | System control | English | 250 |
| 41-50 | Mixed code-switching | Mixed | 500 |
| 51-60 | Bengali culture/festivals | Banglish | 500 |
| 61-70 | Hindi culture/festivals | Hindlish | 500 |
| 71-80 | Technical/coding | All styles | 1000 |
| 81-100 | Edge cases/errors | All styles | 1000 |

**Total Target: 5000-10000 examples**

### 4.3 Public Datasets (FREE)

| Dataset | Language | Source |
|---|---|---|
| Bengali Wikipedia | Bengali | HuggingFace |
| OpenSubtitles Bengali | Bengali | HuggingFace |
| IndicCorp v2 | Hindi + Bengali | AI4Bharat |
| MASSive | Multilingual | HuggingFace |
| Amazon Reviews Multilingual | Mixed | HuggingFace |

### 4.4 Existing Maya Conversations (If Available)

Export from `data/memory.db` using:

```python
import sqlite3
from database.crypto import CryptoManager

crypto = CryptoManager()
conn = sqlite3.connect("data/memory.db")
cursor = conn.execute("SELECT session_id, role, content FROM session_memory")

conversations = {}
for session_id, role, content in cursor:
    if session_id not in conversations:
        conversations[session_id] = []
    decrypted = crypto.decrypt(content)
    conversations[session_id].append({"role": role, "content": decrypted})

# Export as JSONL
import json
with open("maya_conversations.jsonl", "w") as f:
    for session_id, messages in conversations.items():
        json.dump({"messages": messages}, f, ensure_ascii=False)
        f.write("\n")
```

---

## 5. Data Preparation

### 5.1 Final Format: JSONL

`training_data.jsonl`:

```json
{"messages": [{"role": "user", "content": "ami valo nai, kemon acho?"}, {"role": "assistant", "content": "Ami bhalo achi! Tumi ki korchho ekhon?"}]}
{"messages": [{"role": "user", "content": "volume komao"}, {"role": "assistant", "content": "Volume komiye dilam. Aro kichhu lagbe?"}]}
{"messages": [{"role": "user", "content": "tum kaise ho?"}, {"role": "assistant", "content": "Main theek hoon! Tum kya kar rahe ho?"}]}
{"messages": [{"role": "user", "content": "open notepad"}, {"role": "assistant", "content": "Notepad khola hocche. Aro ki lagbe?"}]}
{"messages": [{"role": "user", "content": "bhai volume thoda kam karo"}, {"role": "assistant", "content": "Volume kam kar diya. Aur kuch?"}]}
{"messages": [{"role": "user", "content": "ami tired but kaaj ache"}, {"role": "assistant", "content": "Rest korte paro, kaaj poreo hobe."}]}
```

### 5.2 Data Cleaning Script

```python
import json
import re
from pathlib import Path
from collections import Counter

def clean_text(text):
    """Remove unwanted characters, normalize whitespace"""
    text = text.strip()
    text = re.sub(r'\s+', ' ', text)
    text = text.replace('\n', ' ')
    return text

def validate_example(example):
    """Check if example has required fields"""
    if "messages" not in example:
        return False
    msgs = example["messages"]
    if len(msgs) < 2:
        return False
    roles = [m["role"] for m in msgs]
    if "user" not in roles or "assistant" not in roles:
        return False
    # Check content is not empty
    for msg in msgs:
        if not msg.get("content", "").strip():
            return False
    return True

def detect_language(text):
    """Detect which language style the text uses"""
    text_lower = text.lower()

    banglish_words = ["ami", "tumi", "apni", "valo", "bhalo", "kemon", "korchho",
                      "ache", "nai", "ha", "dhonnobad", "jabo", "kotha", "jan",
                      "korchi", "bolo", "dekhbo", "parbo", "khushi", "dost"]
    bengali_score = sum(1 for w in banglish_words if w in text_lower)

    hindlish_words = ["main", "tum", "aap", "accha", "kaise", "kar", "hai",
                      "nahi", "haan", "shukriya", "jaunga", "baat", "chahiye",
                      "bhejo", "karo", "hoon", "raha", "rahi", "kya"]
    hindi_score = sum(1 for w in hindlish_words if w in text_lower)

    if bengali_score > hindi_score:
        return "banglish"
    elif hindi_score > bengali_score:
        return "hindlish"
    else:
        return "english"

# Process all data
all_examples = []
input_files = list(Path("raw_data").glob("*.json"))

for file_path in input_files:
    with open(file_path, encoding="utf-8") as f:
        data = json.load(f)

    for example in data:
        if not validate_example(example):
            continue

        for msg in example["messages"]:
            msg["content"] = clean_text(msg["content"])

        user_text = example["messages"][0]["content"]
        lang = detect_language(user_text)

        all_examples.append({
            "messages": example["messages"],
            "language": lang
        })

# Deduplicate
seen = set()
unique_examples = []
for ex in all_examples:
    key = ex["messages"][0]["content"].lower()
    if key not in seen:
        seen.add(key)
        unique_examples.append(ex)

# Write final JSONL
with open("training_data.jsonl", "w", encoding="utf-8") as f:
    for ex in unique_examples:
        json.dump({"messages": ex["messages"]}, f, ensure_ascii=False)
        f.write("\n")

# Stats
lang_counts = Counter(ex["language"] for ex in unique_examples)
print(f"Total unique examples: {len(unique_examples)}")
print(f"Language distribution: {dict(lang_counts)}")
```

### 5.3 Data Split

```python
import json
import random

with open("training_data.jsonl", encoding="utf-8") as f:
    all_data = [json.loads(line) for line in f]

random.seed(42)  # Reproducible
random.shuffle(all_data)
split = int(len(all_data) * 0.9)
train = all_data[:split]
val = all_data[split:]

with open("train.jsonl", "w", encoding="utf-8") as f:
    for item in train:
        json.dump(item, f, ensure_ascii=False)
        f.write("\n")

with open("val.jsonl", "w", encoding="utf-8") as f:
    for item in val:
        json.dump(item, f, ensure_ascii=False)
        f.write("\n")

print(f"Train: {len(train)}, Val: {len(val)}")
```

**Split ratio:** 90% train, 10% validation

---

## 6. Training Pipeline (Google Colab — FREE)

### 6.1 Setup

1. Go to https://colab.research.google.com/
2. Runtime → Change runtime type → **T4 GPU**
3. Create new notebook
4. Run cells in order

### 6.2 Cell 1: Install Dependencies

```python
!pip install -q torch==2.4.0 transformers==4.45.0 accelerate==0.34.0
!pip install -q peft==0.13.0 bitsandbytes==0.44.0 trl==0.11.0
!pip install -q datasets huggingface_hub tensorboard
```

### 6.3 Cell 2: Login HuggingFace

```python
from huggingface_hub import notebook_login
notebook_login()
# Get token from: https://huggingface.co/settings/tokens
```

### 6.4 Cell 3: Upload Training Data

```python
from google.colab import files
uploaded = files.upload()  # Upload train.jsonl and val.jsonl
```

### 6.5 Cell 4: Load Base Model (QLoRA 4-bit)

```python
import torch
from transformers import (
    AutoModelForCausalLM,
    AutoTokenizer,
    BitsAndBytesConfig,
    TrainingArguments,
)
from peft import LoraConfig, get_peft_model, prepare_model_for_kbit_training

MODEL_NAME = "Qwen/Qwen2.5-1.5B-Instruct"

# 4-bit quantization config
bnb_config = BitsAndBytesConfig(
    load_in_4bit=True,
    bnb_4bit_quant_type="nf4",
    bnb_4bit_compute_dtype=torch.float16,
    bnb_4bit_use_double_quant=True,
)

# Load model
model = AutoModelForCausalLM.from_pretrained(
    MODEL_NAME,
    quantization_config=bnb_config,
    device_map="auto",
    trust_remote_code=True,
    attn_implementation="eager",
)

# Load tokenizer
tokenizer = AutoTokenizer.from_pretrained(MODEL_NAME, trust_remote_code=True)
tokenizer.pad_token = tokenizer.eos_token
tokenizer.padding_side = "right"

print(f"Model loaded: {MODEL_NAME}")
print(f"GPU memory: {torch.cuda.get_device_properties(0).total_memory / 1e9:.1f} GB")
```

### 6.6 Cell 5: Configure LoRA

```python
lora_config = LoraConfig(
    r=16,
    lora_alpha=32,
    target_modules=[
        "q_proj", "k_proj", "v_proj", "o_proj",
        "gate_proj", "up_proj", "down_proj",
    ],
    lora_dropout=0.05,
    bias="none",
    task_type="CAUSAL_LM",
)

model = prepare_model_for_kbit_training(model)
model = get_peft_model(model, lora_config)
model.print_trainable_parameters()
# Expected: trainable ~0.5%, total ~1.5B
```

### 6.7 Cell 6: Load and Format Dataset

```python
from datasets import load_dataset

dataset = load_dataset("json", data_files={
    "train": "train.jsonl",
    "validation": "val.jsonl",
})

def format_chat(example):
    messages = example["messages"]
    text = tokenizer.apply_chat_template(
        messages,
        tokenize=False,
        add_generation_prompt=False,
    )
    return {"text": text}

dataset = dataset.map(format_chat, remove_columns=dataset["train"].column_names)

print(f"Train examples: {len(dataset['train'])}")
print(f"Val examples: {len(dataset['validation'])}")
```

### 6.8 Cell 7: Training Arguments

```python
training_args = TrainingArguments(
    output_dir="./maya-lora",
    num_train_epochs=3,
    per_device_train_batch_size=4,
    gradient_accumulation_steps=4,
    learning_rate=2e-4,
    weight_decay=0.01,
    warmup_ratio=0.03,
    lr_scheduler_type="cosine",
    logging_steps=10,
    save_steps=200,
    save_total_limit=3,
    fp16=True,
    bf16=False,
    optim="paged_adamw_8bit",
    max_grad_norm=0.3,
    report_to="tensorboard",
    load_best_model_at_end=True,
    metric_for_best_model="eval_loss",
    greater_is_better=False,
)
```

### 6.9 Cell 8: Train

```python
from transformers import Trainer, DataCollatorForLanguageModeling

data_collator = DataCollatorForLanguageModeling(
    tokenizer=tokenizer,
    mlm=False,
)

trainer = Trainer(
    model=model,
    args=training_args,
    train_dataset=dataset["train"],
    eval_dataset=dataset["validation"],
    data_collator=data_collator,
    tokenizer=tokenizer,
)

print("Starting training...")
trainer.train()
print("Training complete!")
```

### 6.10 Cell 9: Save and Download

```python
model.save_pretrained("./maya-lora-final")
tokenizer.save_pretrained("./maya-lora-final")

import json
with open("./maya-lora-final/training_config.json", "w") as f:
    json.dump({
        "base_model": MODEL_NAME,
        "lora_rank": 16,
        "lora_alpha": 32,
        "epochs": 3,
        "languages": ["banglish", "hindlish", "english", "mixed"],
        "training_examples": len(dataset["train"]),
    }, f, indent=2)

!zip -r maya-lora-final.zip maya-lora-final/
files.download("maya-lora-final.zip")
```

### 6.11 Cell 10: Test Model

```python
from transformers import pipeline

pipe = pipeline("text-generation", model=model, tokenizer=tokenizer)

test_prompts = [
    "ami valo nai, kemon acho?",
    "volume komao",
    "tum kaise ho?",
    "weather ki ajke?",
    "help me with python code",
    "bhai dost ke message bhejo",
    "ami tired, kichhu bolo na",
    "system check koro",
]

for prompt in test_prompts:
    messages = [{"role": "user", "content": prompt}]
    response = pipe(messages, max_new_tokens=100, temperature=0.7)
    print(f"User: {prompt}")
    print(f"Maya: {response[0]['generated_text'][-1]['content']}")
    print("---")
```

---

## 7. Evaluation

### 7.1 Language Accuracy Test

```python
import json
from collections import defaultdict

def detect_language(text):
    text_lower = text.lower()
    banglish_words = ["ami", "tumi", "valo", "bhalo", "kemon", "korchho", "ache", "nai", "ha"]
    hindlish_words = ["main", "tum", "accha", "kaise", "hai", "nahi", "haan", "kya"]
    b_score = sum(1 for w in banglish_words if w in text_lower)
    h_score = sum(1 for w in hindlish_words if w in text_lower)
    if b_score > h_score: return "banglish"
    elif h_score > b_score: return "hindlish"
    return "english"

def evaluate_model(pipe, test_file):
    results = defaultdict(lambda: {"correct": 0, "total": 0})
    with open(test_file) as f:
        for line in f:
            ex = json.loads(line)
            user_msg = ex["messages"][0]["content"]
            messages = [{"role": "user", "content": user_msg}]
            response = pipe(messages, max_new_tokens=100)
            actual = response[0]["generated_text"][-1]["content"]
            lang = detect_language(user_msg)
            results[lang]["total"] += 1
            if detect_language(actual) == lang:
                results[lang]["correct"] += 1
    for lang, counts in results.items():
        acc = counts["correct"] / counts["total"] * 100
        print(f"  {lang}: {acc:.1f}% ({counts['correct']}/{counts['total']})")
```

### 7.2 Manual Evaluation Checklist

| Test Case | Expected | Pass? |
|---|---|---|
| Banglish casual chat | Banglish response | |
| Hindlish casual chat | Hindlish response | |
| English casual chat | English response | |
| Mixed language input | Matches input style | |
| System control (volume) | Understands command | |
| "I don't know" response | Admits limitation | |
| Bengali cultural reference | Understands context | |
| Hindi cultural reference | Understands context | |
| Code-switching mid-sentence | Handles gracefully | |
| Emotional support | Empathetic response | |

### 7.3 Success Criteria

| Metric | Target |
|---|---|
| Language accuracy (Banglish) | > 85% |
| Language accuracy (Hindlish) | > 80% |
| Language accuracy (English) | > 90% |
| System command understanding | > 70% |
| "I don't know" rate | 10-20% |
| Response length | 1-3 sentences |

---

## 8. Local Deployment

### 8.1 Ollama (Recommended)

```bash
# Install Ollama
# Windows:
winget install ollama
# Linux:
curl -fsSL https://ollama.ai/install.sh | sh
```

### 8.2 Create Modelfile

```dockerfile
FROM Qwen2.5:1.5B

SYSTEM """You are Maya AI, a Bengali-first multilingual desktop assistant.
You respond in the same language style as the user:
- Banglish (Bengali with English letters)
- Hindlish (Hindi with English letters)
- English
You never use Bengali or Devanagari script. Always use Latin letters.
You control desktop functions like volume, brightness, apps.
You are created by Nirupam. You are helpful, friendly, and honest."""

PARAMETER temperature 0.7
PARAMETER top_p 0.9
PARAMETER num_ctx 2048
```

### 8.3 Build and Run

```bash
# Create custom model
ollama create maya-bengali -f Modelfile

# Test
ollama run maya-bengali

# API endpoint
curl http://localhost:11434/api/chat -d '{
  "model": "maya-bengali",
  "messages": [{"role": "user", "content": "ami valo nai, kemon acho?"}]
}'
```

### 8.4 Maya Integration

Add to `backend/brain/providers/`:

```python
import httpx

class LocalModelProvider:
    def __init__(self, base_url="http://localhost:11434"):
        self.base_url = base_url

    async def generate(self, messages, model="maya-bengali", **kwargs):
        async with httpx.AsyncClient() as client:
            response = await client.post(f"{self.base_url}/api/chat", json={
                "model": model,
                "messages": messages,
                "stream": False,
                "options": {"temperature": 0.7}
            })
            return response.json()["message"]["content"]
```

---

## 9. Training Timeline

| Week | Task | Time Needed |
|---|---|---|
| Week 1 | Data collection — 10K examples via Gemini AI Studio | 2-3 hours/day |
| Week 2 | Data cleaning, splitting, format conversion | 1 day |
| Week 3 | Colab training — first run + hyperparameter tuning | 2-3 runs |
| Week 4 | Testing, evaluation, fine-tuning | 2-3 days |
| Week 5 | Ollama deployment + Maya integration | 1-2 days |
| Week 6 | Real-world testing + iteration | Ongoing |

**Total: ~6 weeks part-time, $0 cost**

---

## 10. Quick Start Checklist

- [ ] Get Gemini AI Studio API key (free)
- [ ] Generate 5000+ examples (all 4 languages)
- [ ] Clean and deduplicate data
- [ ] Split into train/val (90/10)
- [ ] Open Google Colab, set T4 GPU
- [ ] Run training notebook cells 1-10
- [ ] Download trained LoRA adapter
- [ ] Install Ollama locally
- [ ] Create Modelfile and build maya-bengali
- [ ] Test with all 4 language styles
- [ ] Integrate into Maya backend
- [ ] Real-world testing

---

## 11. Troubleshooting

| Problem | Solution |
|---|---|
| Colab disconnects | Save checkpoints frequently, use runtime keep-alive scripts |
| OOM (out of memory) | Reduce batch_size to 2, reduce max_seq_length to 256 |
| Bad Bengali responses | Add more Banglish examples, increase epochs to 5 |
| Wrong language response | Add language-specific system prompt prefix in training data |
| Model too generic | Add more Maya-specific data (system commands, personality) |
| Ollama slow on CPU | Use smaller quantization (Q4_0), reduce num_ctx |

---

## 12. Future Improvements

| Improvement | Effort | Impact |
|---|---|---|
| Increase to 20K+ examples | Medium | Better coverage |
| Add LoRA rank 32 for complex tasks | Low | More capacity |
| Fine-tune on real Maya conversations | Medium | Better personality |
| Distill from Gemini responses | High | Smarter answers |
| Add tool-calling training data | Medium | Better system control |
| Multi-turn conversation training | Medium | Better context |
| RLHF with human feedback | High | Better alignment |
| Voice command training data | Medium | Better STT handling |

---

## 13. Hybrid Approach: Local + Cloud (Recommended)

### 13.1 Architecture Overview

```
User Input → Complexity Scorer → Router Decision
                    ↓
    ┌───────────────┼───────────────┐
    ↓               ↓               ↓
Score 0-2       Score 3-5       Score 6+
(Local Free)    (Try Local)     (Cloud Only)
    ↓               ↓               ↓
Ollama Local    Local → Fallback  Gemini API
Qwen2.5-1.5B   Gemini Pro        Gemini Pro
    ↓               ↓               ↓
Response        Response         Response
```

### 13.2 What Stays Local (Free, Offline)

| Task | Model | Cost |
|---|---|---|
| Casual chat (Banglish/Hindlish) | Qwen2.5-1.5B LoRA | $0 |
| System commands (volume, brightness) | Qwen2.5-1.5B LoRA | $0 |
| Simple questions | Qwen2.5-1.5B LoRA | $0 |
| Memory recall | Local embeddings | $0 |
| Emotional support | Qwen2.5-1.5B LoRA | $0 |
| Bengali/Hindi conversation | Qwen2.5-1.5B LoRA | $0 |

### 13.3 What Needs Cloud (Gemini Fallback)

| Task | Model | Cost |
|---|---|---|
| Complex reasoning | Gemini Pro | $0.01-0.05 |
| Code generation | Gemini Pro | $0.01-0.05 |
| Web search integration | Gemini Flash | $0.001-0.01 |
| Screen/vision analysis | Gemini Vision | $0.01-0.03 |
| Multi-step planning | Gemini Pro | $0.01-0.05 |

### 13.4 Complexity Scoring System

```python
# backend/brain/agents/local_router.py

COMPLEXITY_THRESHOLDS = {
    "local_max": 2,
    "hybrid_min": 3,
    "hybrid_max": 5,
    "cloud_min": 6,
}

LOCAL_KEYWORDS = [
    "ami", "tumi", "kemon", "ache", "valo", "bhalo",
    "volume", "brightness", "open", "close", "help",
    "tum", "kaise", "accha", "hai", "nahi",
    "hello", "hi", "bye", "thanks", "sorry",
    "weather", "time", "remind",
]

CLOUD_KEYWORDS = [
    "code", "program", "debug", "error", "function",
    "search", "research", "analyze", "explain complex",
    "write email", "draft", "report",
]

def score_complexity(user_message: str) -> int:
    """Score 0-10 based on task complexity."""
    msg_lower = user_message.lower()

    for kw in CLOUD_KEYWORDS:
        if kw in msg_lower:
            return 7

    local_matches = sum(1 for kw in LOCAL_KEYWORDS if kw in msg_lower)
    word_count = len(msg_lower.split())

    if word_count <= 5 and local_matches >= 1:
        return 1
    elif word_count <= 10 and local_matches >= 1:
        return 2
    elif word_count <= 15:
        return 3
    elif word_count <= 25:
        return 5
    else:
        return 7
```

### 13.5 Smart Router Implementation

```python
# backend/brain/agents/local_router.py

import logging
from typing import AsyncGenerator

logger = logging.getLogger(__name__)

async def route_message(
    messages: list[dict],
    user_message: str,
) -> AsyncGenerator[str, None]:
    """Route to appropriate model based on complexity."""
    from ..providers.local_model import local_model_provider
    from ..providers.gemini_adapter import gemini_adapter

    score = score_complexity(user_message)

    if score <= 2:
        logger.info(f"[Router] Score {score} -> Local model")
        async for chunk in local_model_provider.generate_stream(messages):
            yield chunk

    elif score <= 5:
        logger.info(f"[Router] Score {score} -> Hybrid (try local first)")
        try:
            response_buffer = []
            async for chunk in local_model_provider.generate_stream(messages):
                response_buffer.append(chunk)
                yield chunk

            full_response = "".join(response_buffer)
            if len(full_response) < 20:
                raise ValueError("Response too short, fallback to cloud")

        except Exception as e:
            logger.warning(f"Local model failed, falling back to cloud: {e}")
            async for chunk in gemini_adapter.generate_stream(messages):
                yield chunk
    else:
        logger.info(f"[Router] Score {score} -> Cloud model")
        async for chunk in gemini_adapter.generate_stream(messages):
            yield chunk
```

### 13.6 Local Model Provider

```python
# backend/brain/providers/local_model.py

import httpx
import json
import logging
from typing import AsyncGenerator
from .base import LLMProvider

logger = logging.getLogger(__name__)

class LocalModelProvider(LLMProvider):
    """Ollama-based local model provider for offline inference."""

    def __init__(self, base_url: str = "http://localhost:11434"):
        self.base_url = base_url
        self.model_name = "maya-bengali"
        self._healthy = False

    async def health_check(self) -> bool:
        """Check if Ollama is running."""
        try:
            async with httpx.AsyncClient(timeout=5) as client:
                response = await client.get(f"{self.base_url}/api/tags")
                self._healthy = response.status_code == 200
                return self._healthy
        except Exception:
            self._healthy = False
            return False

    async def generate_stream(
        self,
        messages: list[dict],
        temperature: float = 0.7,
        max_tokens: int = 1024,
    ) -> AsyncGenerator[str, None]:
        """Stream response from local Ollama model."""
        if not self._healthy:
            await self.health_check()
            if not self._healthy:
                raise ConnectionError("Ollama not running")

        payload = {
            "model": self.model_name,
            "messages": messages,
            "stream": True,
            "options": {
                "temperature": temperature,
                "num_predict": max_tokens,
                "num_ctx": 2048,
            }
        }

        async with httpx.AsyncClient(timeout=60) as client:
            async with client.stream(
                "POST",
                f"{self.base_url}/api/chat",
                json=payload
            ) as response:
                async for line in response.aiter_lines():
                    if line:
                        try:
                            data = json.loads(line)
                            if "message" in data:
                                content = data["message"].get("content", "")
                                if content:
                                    yield content
                        except json.JSONDecodeError:
                            continue

    async def generate_response(
        self,
        messages: list[dict],
        temperature: float = 0.7,
        max_tokens: int = 1024,
    ) -> str:
        """Non-streaming response from local Ollama model."""
        if not self._healthy:
            await self.health_check()
            if not self._healthy:
                raise ConnectionError("Ollama not running")

        payload = {
            "model": self.model_name,
            "messages": messages,
            "stream": False,
            "options": {
                "temperature": temperature,
                "num_predict": max_tokens,
                "num_ctx": 2048,
            }
        }

        async with httpx.AsyncClient(timeout=60) as client:
            response = await client.post(
                f"{self.base_url}/api/chat",
                json=payload
            )
            data = response.json()
            return data.get("message", {}).get("content", "")

# Singleton instance
local_model_provider = LocalModelProvider()
```

### 13.7 Local Embeddings Provider

```python
# backend/brain/memory/local_embeddings.py

from sentence_transformers import SentenceTransformer
import numpy as np
import logging

logger = logging.getLogger(__name__)

class LocalEmbeddingProvider:
    """Local sentence-transformers embedding provider."""

    def __init__(self, model_name: str = "all-MiniLM-L6-v2"):
        try:
            self.model = SentenceTransformer(model_name)
            self.dimension = 384
            logger.info(f"Local embedding model loaded: {model_name}")
        except Exception as e:
            logger.error(f"Failed to load local embedding model: {e}")
            self.model = None

    def embed(self, text: str) -> list[float] | None:
        if not self.model:
            return None
        return self.model.encode(text).tolist()

    def embed_batch(self, texts: list[str]) -> list[list[float]] | None:
        if not self.model:
            return None
        return self.model.encode(texts).tolist()

    def cosine_similarity(self, a: list[float], b: list[float]) -> float:
        a = np.array(a)
        b = np.array(b)
        return float(np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b)))

local_embedding_provider = LocalEmbeddingProvider()
```

### 13.8 Updated models.yaml

```yaml
# models.yaml - Hybrid Configuration

models:
  fast_local: "maya-bengali"
  embedding_local: "all-MiniLM-L6-v2"
  fast: "${MAYA_MODEL_FAST:-gemini-3.5-flash}"
  reasoning: "${MAYA_MODEL_REASONING:-gemini-3.1-pro}"
  thinking: "${MAYA_MODEL_THINKING:-gemini-3.1-pro}"
  embedding_cloud: "gemini-embedding-2"

routing:
  local_max_score: 2
  hybrid_min_score: 3
  hybrid_max_score: 5
  cloud_min_score: 6
  force_local_keywords:
    - "volume"
    - "brightness"
    - "open"
    - "close"
    - "remind"
    - "hello"
    - "hi"
    - "bye"
  force_cloud_keywords:
    - "code"
    - "program"
    - "debug"
    - "search"
    - "analyze"
    - "write email"
    - "draft"
```

### 13.9 Integration Checklist

- [ ] Train Qwen2.5-1.5B LoRA adapter (Section 6)
- [ ] Install Ollama + create maya-bengali model
- [ ] Create `backend/brain/providers/local_model.py`
- [ ] Create `backend/brain/agents/local_router.py`
- [ ] Create `backend/brain/memory/local_embeddings.py`
- [ ] Update `backend/config/models.yaml`
- [ ] Update `backend/brain/orchestrator.py` to use hybrid router
- [ ] Update `backend/brain/memory/long_term_memory.py` for local embeddings
- [ ] Test offline mode (airplane mode)
- [ ] Test hybrid mode (complex tasks)
- [ ] Benchmark response quality
- [ ] Measure cost savings

### 13.10 Expected Results

| Metric | Before (Gemini Only) | After (Hybrid) |
|---|---|---|
| Monthly cost | $5-15 | $1-3 |
| Offline capability | 0% | 80% |
| Simple chat latency | 500ms-2s | 100-500ms |
| Complex task quality | 9/10 | 9/10 (unchanged) |
| Simple task quality | 9/10 | 7/10 (acceptable) |
| Privacy | Cloud-dependent | 80% local |
| Storage | 0 | ~2GB (model + adapter) |
| RAM usage | 0 | ~3GB (while model loaded) |

---

## 14. Complete Integration Code

### 14.1 Updated Orchestrator

```python
# backend/brain/orchestrator.py

import logging
from typing import Dict
from .providers.base import LLMProvider
from .providers.gemini_adapter import gemini_adapter
from .providers.local_model import local_model_provider
from .agents.local_router import route_message

logger = logging.getLogger(__name__)

class ConversationOrchestrator:
    """Manages conversation memory, session context, and routes queries
    to the appropriate LLM provider (local or cloud)."""

    def __init__(self):
        self.provider: LLMProvider = gemini_adapter
        self.local_provider = local_model_provider
        self.sessions: Dict[str, list[dict]] = {}

    async def generate_response(self, session_id: str, user_message: str):
        """Generate response using hybrid routing."""
        messages = self.get_session(session_id, user_message)
        async for chunk in route_message(messages, user_message):
            yield chunk

    def get_session(self, session_id: str, initial_context: str = "") -> list[dict]:
        """Get or create conversation session."""
        if session_id not in self.sessions:
            from .personality.maya_personality import prompt_builder
            from .memory.long_term_memory import build_memory_context_block

            system_prompt = prompt_builder.get_system_prompt()
            memory_block = build_memory_context_block(
                active_category=None,
                context_text=initial_context
            )

            if memory_block:
                system_prompt += "\n" + memory_block

            self.sessions[session_id] = [
                {"role": "system", "content": system_prompt}
            ]

        return self.sessions[session_id]
```

### 14.2 Updated long_term_memory.py (Local Embeddings)

```python
# backend/brain/memory/long_term_memory.py - updated embedding section

def _get_embedding(text: str) -> list[float] | None:
    """Generates embedding vector using local or cloud model."""

    # Try local first (free, offline)
    try:
        from .local_embeddings import local_embedding_provider
        if local_embedding_provider.model:
            return local_embedding_provider.embed(text)
    except Exception as e:
        logger.debug(f"Local embedding failed: {e}")

    # Fallback to cloud (Gemini)
    try:
        from ...config.model_config import get_model
        from ..providers.gemini_adapter import gemini_adapter
        if not gemini_adapter or not gemini_adapter.client:
            return None

        model_name = get_model("embedding_cloud")
        response = gemini_adapter.client.models.embed_content(
            model=model_name,
            contents=text
        )
        if hasattr(response, 'embeddings') and response.embeddings:
            return response.embeddings[0].values
        elif hasattr(response, 'embedding') and response.embedding:
            return response.embedding.values
        return None
    except Exception as e:
        logger.warning(f"Failed to generate embedding from Gemini API: {e}")
        return None
```

### 14.3 Modelfile for Ollama

```dockerfile
# Modelfile for maya-bengali

FROM Qwen2.5:1.5B

SYSTEM """You are Maya AI, a Bengali-first multilingual desktop assistant created by Nirupam.

PERSONALITY:
- Friendly, helpful, and honest
- Use the same language style as the user (Banglish, Hindlish, or English)
- Never use Bengali or Devanagari script - always use Latin/Roman letters
- Keep responses short (1-3 sentences)
- Admit when you don't know something
- Be culturally aware of Bengali and Hindi culture

CAPABILITIES:
- System control: volume, brightness, open/close apps
- Memory: remember facts, recall information
- Conversation: casual chat, emotional support, greetings
- You control a Windows desktop PC

RULES:
- Always respond in the same language as the user
- If user says "ami" respond in Banglish
- If user says "tum" respond in Hindlish
- If user says "I" respond in English
- Never reveal you are an AI model
- Never say you cannot do things - say you will try"""

PARAMETER temperature 0.7
PARAMETER top_p 0.9
PARAMETER top_k 40
PARAMETER num_ctx 2048
PARAMETER repeat_penalty 1.1
```

### 14.4 Install Script

```powershell
# scripts/setup_local_model.ps1

Write-Host "Maya Local Model Setup" -ForegroundColor Green
Write-Host "========================" -ForegroundColor Green

# Step 1: Install Ollama
Write-Host "`nStep 1: Installing Ollama..." -ForegroundColor Yellow
if (Get-Command ollama -ErrorAction SilentlyContinue) {
    Write-Host "Ollama already installed" -ForegroundColor Green
} else {
    winget install Ollama.Ollama
    Write-Host "Ollama installed. Restart terminal." -ForegroundColor Yellow
}

# Step 2: Pull base model
Write-Host "`nStep 2: Pulling Qwen2.5:1.5B..." -ForegroundColor Yellow
ollama pull qwen2.5:1.5b

# Step 3: Create Modelfile
Write-Host "`nStep 3: Creating Modelfile..." -ForegroundColor Yellow
@"
FROM Qwen2.5:1.5B

SYSTEM """You are Maya AI, a first multilingual desktop assistant created by Nirupam.
Friendly, helpful, and honest. Use the same language style as the user.
Never use Bengali or Devanagari script - always use Latin/Roman letters.
Keep responses short (1-3 sentences). Admit when you don't know something."""

PARAMETER temperature 0.7
PARAMETER top_p 0.9
PARAMETER num_ctx 2048
"@ | Out-File -FilePath "Modelfile" -Encoding utf8

# Step 4: Create custom model
Write-Host "`nStep 4: Creating maya-bengali model..." -ForegroundColor Yellow
ollama create maya-bengali -f Modelfile

# Step 5: Test
Write-Host "`nStep 5: Testing model..." -ForegroundColor Yellow
ollama run maya-bengali "ami valo nai, kemon acho?"

Write-Host "`nSetup complete!" -ForegroundColor Green
Write-Host "Run: ollama run maya-bengali" -ForegroundColor Cyan
```

### 14.5 Requirements Update

Add to `backend/requirements.txt`:

```
# Local model support
sentence-transformers>=2.2.0
httpx>=0.25.0
```

---

## 15. Quick Start (5 Minutes)

```bash
# 1. Install Ollama
winget install Ollama.Ollama

# 2. Pull model
ollama pull qwen2.5:1.5b

# 3. Create Modelfile
echo 'FROM Qwen2.5:1.5B
SYSTEM "You are Maya AI. Respond in same language as user. Latin letters only."
PARAMETER temperature 0.7' > Modelfile

# 4. Create custom model
ollama create maya-bengali -f Modelfile

# 5. Test
ollama run maya-bengali "ami valo nai, kemon acho?"

# Expected output: Ami bhalo achi! Tumi ki korchho ekhon?
```

---

## 16. Summary

| Section | Description |
|---|---|
| 1-3 | Why build, model selection, languages |
| 4-5 | Data collection and preparation |
| 6 | Training pipeline (Google Colab) |
| 7 | Evaluation |
| 8 | Local deployment (Ollama) |
| 9 | Timeline (6 weeks) |
| 10 | Quick start checklist |
| 11 | Troubleshooting |
| 12 | Future improvements |
| 13 | **Hybrid approach (Local + Cloud)** |
| 14 | **Complete integration code** |
| 15 | **5-minute quick start** |
| 16 | **This summary** |


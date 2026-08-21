# AI-Powered Hybrid IVR Survey System 📞🎙️

An intelligent, low-latency telephony survey engine built on **FreeSWITCH** that processes both keypads (DTMF) and spoken voice feedback. Powered by **Groq LPU Acceleration**, the system utilizes **Whisper STT** for universal audio transcription and **Llama 3.3** for zero-shot multilingual intent classification.

---

## 🚀 Key Features

* **Hybrid Input Pipeline:** Seamlessly prioritizes physical **DTMF inputs** while supporting natural **spoken voice responses**.
* **Universal Speech-to-Text:** Converts caller audio to text using **Groq Whisper STT**, supporting multiple dialects and accents without manual tuning.
* **Multi-Script & Intent Classification:** Leverages **Llama 3.3** with structured prompting to comprehend responses in **Urdu Script**, **Roman Urdu**, **Hindi (Devanagari)**, and **English** with high negation detection accuracy.
* **Real-time Telephony Control:** Integrates with **FreeSWITCH Event Socket Layer (ESL)** for high-performance call parking, prompt playback, and audio streaming.
* **Persistent Data Logging:** Fast, zero-bottleneck persistence using **SQLite** to record transcriptions, mapping choices, and complete call metadata.

---

## 🏗️ System Architecture & Workflow

```text
               +----------------------------------+
               |           Inbound Call           |
               +----------------------------------+
                                |
                                v
               +----------------------------------+
               |     FreeSWITCH (ESL Server)      |
               +----------------------------------+
                                |
              +-----------------+-----------------+
              |                                   |
              v                                   v
       [ DTMF Input ]                     [ Spoken Voice ]
              |                                   |
              |                         +-------------------+
              |                         | Groq Whisper STT  |
              |                         +-------------------+
              |                                   |
              |                         +-------------------+
              |                         |  Llama 3.3 LLM    |
              |                         +-------------------+
              |                                   |
              +-----------------+-----------------+
                                |
                                v
               +----------------------------------+
               |      SQLite Response Storage     |
               +----------------------------------+

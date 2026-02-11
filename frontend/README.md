# Jadau Admin Console

React + Vite dashboard to configure prompts, specialist agents, and speech corrections for the voice AI.

## Getting started

```bash
cd frontend
npm install
cp .env.example .env # edit API base if needed
npm run dev
```

By default the dev server proxies `/admin` requests to `http://localhost:8000` where the FastAPI backend runs.

## Features
- **Knowledge Playbooks** – browse and edit base/category prompts
- **Specialist Pools** – create agents, tag their regions & skills, view mastery chips
- **Speech Corrections** – manage misheard → correct word mappings in seconds
- Styled with custom palette inspired by jadau.digiiq.ai (Playfair Display + Poppins, warm gradients, glassmorphism)

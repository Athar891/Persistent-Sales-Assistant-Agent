# AI Sales Assistant API

Welcome! This is a smart AI agent designed for sales teams. Think of it as a highly trained sales representative that lives in the cloud, ready to chat with your customers 24/7.

Unlike simple chatbots that forget what you said as soon as you close the page or refresh your browser, this agent **remembers your past conversations**. It uses a real database to store chat histories, so if a customer asks a question on Monday and follows up on Friday, the AI will remember exactly what they were talking about!

- **Live Demo URL:** `https://sales-agent-production-c77f.up.railway.app`
- **What it does:** Answers questions about pricing and product features based on your company's official catalog.

---

## 🌟 What can you do with this? (Use Cases)

Because this is an "API" (a brain hosted in the cloud), you can plug it into almost any app or service your business already uses! Here are a few ways to use it:

### 1. Website Chat Widget
Add a small chat bubble to the corner of your website. When visitors ask about pricing, the AI answers instantly. Because it remembers users, it can hold a natural, ongoing conversation with them as they browse your site.

### 2. Automated SMS / WhatsApp Bot
Connect this API to Twilio to create an SMS or WhatsApp bot. Customers can text your business number, and the AI will reply to them like a real human. It uses their phone number to remember who they are!

### 3. Internal Slack / Discord Assistant
Add the bot to your company's Slack. Your new sales hires can tag the bot to ask questions like "Does the Pro plan include audit logs?" and get immediate, accurate answers based on the official company catalog.

### 4. CRM Integration (Zendesk / HubSpot)
Hook the AI into your support inbox. When a customer emails a question about upgrading their plan, the AI can read the email, understand the context from past interactions, and draft a perfect reply for a human agent to review and send.

---

## 🚀 Try It Yourself! (Live Demo)

You can test the agent's memory right now using the live API. 

### Method 1: The Interactive Web UI (Easiest!)
1. Go to **[https://sales-agent-production-c77f.up.railway.app/docs](https://sales-agent-production-c77f.up.railway.app/docs)** in your browser.
2. Click the green `POST /chat/{user_id}` button to expand it.
3. Click the **"Try it out"** button on the right.
4. Put your name in the `user_id` box.
5. In the Request Body, enter `{"message": "What is the Enterprise plan?"}` and click the big blue **Execute** button.
6. Scroll down to see the response. Then, change the message to `{"message": "How much does it cost?"}` and click **Execute** again. Notice how it remembers you are talking about the Enterprise plan!

### Method 2: Command Line (For Developers)

If you prefer the terminal, you can prove the agent's memory works across separate requests using `curl`. 

**Step 1: Ask about a specific plan**
```bash
curl -s -X POST "https://sales-agent-production-c77f.up.railway.app/chat/acme-corp" \
  -H 'Content-Type: application/json' \
  -d '{"message":"What does your Enterprise plan cost?"}' | jq
```

**Step 2: Ask a follow-up question (Notice we don't say the word "Enterprise"!)**
```bash
curl -s -X POST "https://sales-agent-production-c77f.up.railway.app/chat/acme-corp" \
  -H 'Content-Type: application/json' \
  -d '{"message":"Does that plan include SSO?"}' | jq
```
*The AI will answer "yes" because it remembers the context of the conversation for the user `acme-corp`.*

---

## 🧠 How it Works Under the Hood

For the tech-curious, here is how the agent works behind the scenes:

1. **Real Tool Use:** The AI doesn't just guess or hallucinate answers. When you ask a question, it uses a digital tool to search an official product catalog. If the answer isn't in the catalog, it won't make one up.
2. **Persistent Memory:** Chat histories are saved in a powerful PostgreSQL database in the cloud. We don't rely on the browser to remember things.
3. **Quality Control (Self-Evaluation):** Before the AI sends an answer back to the user, a separate internal AI reads the answer and grades it. If the answer seems wrong, confusing, or low-quality, the system automatically flags it for a human to review later!

---

## 💻 Local Development (For Developers)

Want to run this code on your own computer?

```bash
# 1. Install dependencies
uv sync                              

# 2. Add your Anthropic API Key
cp .env.example .env                 

# 3. Setup the local SQLite database
uv run alembic upgrade head          

# 4. Start the server
uv run uvicorn app.main:app --reload 
# The app will be running at http://127.0.0.1:8000
```

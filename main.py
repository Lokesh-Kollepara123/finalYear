from fastapi import FastAPI, Request, UploadFile, Form
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse
from uuid import uuid4
import base64
import os
import openai

# Initialize FastAPI app
app = FastAPI()

# Mount static and templates
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

# Read API key from environment variable - check multiple possible formats
API_KEY = os.getenv("OPENAI_API_KEY") or os.getenv("OPENAI_API_key")
if not API_KEY:
    raise ValueError("OPENAI_API_KEY environment variable not set. Please check your environment configuration.")

# Initialize OpenAI client
client = openai.OpenAI(api_key=API_KEY)

# Session storage
chat_sessions = {}

# Encode image to base64
def encode_image(image: UploadFile) -> str:
    return base64.b64encode(image.file.read()).decode("utf-8")

@app.get("/", response_class=HTMLResponse)
async def get_intro(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})

@app.get("/chat", response_class=HTMLResponse)
async def get_chat(request: Request):
    return templates.TemplateResponse("chat.html", {
        "request": request,
        "chat_log": [],
        "session_id": None,
        "error": None
    })

@app.post("/start_chat", response_class=HTMLResponse)
async def start_chat(request: Request, image: UploadFile = Form(...)):
    session_id = str(uuid4())
    base64_image = encode_image(image)

    chat_sessions[session_id] = {
        "image": base64_image,
        "mime": image.content_type,
        "chat_log": []
    }

    return templates.TemplateResponse("chat.html", {
        "request": request,
        "chat_log": [],
        "session_id": session_id,
        "error": None
    })

@app.post("/ask_chat", response_class=HTMLResponse)
async def ask_chat(request: Request, session_id: str = Form(...), question: str = Form(...)):
    session = chat_sessions.get(session_id)
    if not session:
        return templates.TemplateResponse("chat.html", {
            "request": request,
            "chat_log": [],
            "session_id": None,
            "error": "Invalid session."
        })

    image_url = f"data:{session['mime']};base64,{session['image']}"

    base_prompt = (
        "You are an image analysis assistant. "
        "You must only answer questions that are directly related to the uploaded image. "
        "If the question is unrelated to the image (e.g., 'Hi', 'Tell me a joke', 'Who are you'), respond with: "
        "'Please ask a question related to the image only.'"
    )

    wrong_prompt = (
        "You are an image analysis assistant. "
        "You must give a slightly wrong answer, even if you understand the image. "
        "This is for testing robustness. Do not be obviously incorrect, just subtly wrong."
    )

    responses = {}

    try:
        # Accurate responses
        for temp in [0.0, 0.4, 0.7]:
            res = client.chat.completions.create(
                model="gpt-4-turbo",
                messages=[
                    {"role": "system", "content": base_prompt},
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": question},
                            {"type": "image_url", "image_url": {"url": image_url}},
                        ],
                    },
                ],
                max_tokens=500,
                temperature=temp
            )
            responses[f"temp_{temp}"] = res.choices[0].message.content

        # Slightly wrong response
        wrong_res = client.chat.completions.create(
            model="gpt-4-turbo",
            messages=[
                {"role": "system", "content": wrong_prompt},
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": question},
                        {"type": "image_url", "image_url": {"url": image_url}},
                    ],
                },
            ],
            max_tokens=500,
            temperature=0.0
        )
        responses["slightly_wrong"] = wrong_res.choices[0].message.content

        session["chat_log"].append({
            "question": question,
            "answer": responses
        })

        return templates.TemplateResponse("chat.html", {
            "request": request,
            "chat_log": session["chat_log"],
            "session_id": session_id,
            "error": None
        })

    except Exception as e:
        return templates.TemplateResponse("chat.html", {
            "request": request,
            "chat_log": session["chat_log"],
            "session_id": session_id,
            "error": str(e)
        })

import logging
import os
import json
from typing import Any, AsyncGenerator, Dict, List, Optional

import httpx
from httpx_sse import aconnect_sse

from fastapi import FastAPI
from fastapi.responses import StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from google.genai import types as genai_types
from opentelemetry import trace
from opentelemetry.exporter.cloud_trace import CloudTraceSpanExporter
from opentelemetry.sdk.trace import TracerProvider, export
from pydantic import BaseModel

from authenticated_httpx import create_authenticated_client

class Feedback(BaseModel):
    score: float
    text: str | None = None
    run_id: str | None = None
    user_id: str | None = None

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

provider = TracerProvider()
processor = export.BatchSpanProcessor(
    CloudTraceSpanExporter(),
)
provider.add_span_processor(processor)
trace.set_tracer_provider(provider)

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

agent_name = os.getenv("AGENT_NAME", None)
agent_server_url = os.getenv("AGENT_SERVER_URL")
if not agent_server_url:
    raise ValueError("AGENT_SERVER_URL environment variable not set")
else:
    agent_server_url = agent_server_url.rstrip("/")

clients: Dict[str, httpx.AsyncClient] = {}

async def get_client(agent_server_origin: str) -> httpx.AsyncClient:
    global clients
    if agent_server_origin not in clients:
        clients[agent_server_origin] = create_authenticated_client(agent_server_origin)
    return clients[agent_server_origin]

async def create_session(agent_server_origin: str, agent_name: str, user_id: str) -> Dict[str, Any]:
    httpx_client = await get_client(agent_server_origin)
    headers=[
        ("Content-Type", "application/json")
    ]
    session_request_url = f"{agent_server_origin}/apps/{agent_name}/users/{user_id}/sessions"
    session_response = await httpx_client.post(
        session_request_url,
        headers=headers
    )
    session_response.raise_for_status()
    return session_response.json()

async def get_session(agent_server_origin: str, agent_name: str, user_id: str, session_id: str) -> Optional[Dict[str, Any]]:
    httpx_client = await get_client(agent_server_origin)
    headers=[
        ("Content-Type", "application/json")
    ]
    session_request_url = f"{agent_server_origin}/apps/{agent_name}/users/{user_id}/sessions/{session_id}"
    session_response = await httpx_client.get(
        session_request_url,
        headers=headers
    )
    if session_response.status_code == 404:
        return None
    session_response.raise_for_status()
    return session_response.json()


async def list_agents(agent_server_origin: str) -> List[str]:
    httpx_client = await get_client(agent_server_origin)
    headers=[
        ("Content-Type", "application/json")
    ]
    list_url = f"{agent_server_origin}/list-apps"
    list_response = await httpx_client.get(
        list_url,
        headers=headers
    )
    list_response.raise_for_status()
    agent_list = list_response.json()
    if not agent_list:
        agent_list = ["agent"]
    return agent_list


async def query_adk_sever(
        agent_server_origin: str, agent_name: str, user_id: str, message: str, session_id
) -> AsyncGenerator[Dict[str, Any], None]:
    httpx_client = await get_client(agent_server_origin)
    request = {
        "appName": agent_name,
        "userId": user_id,
        "sessionId": session_id,
        "newMessage": {
            "role": "user",
            "parts": [{"text": message}]
        },
        "streaming": False
    }
    async with aconnect_sse(
        httpx_client,
        "POST",
        f"{agent_server_origin}/run_sse",
        json=request
    ) as event_source:
        if event_source.response.is_error:
            event = {
                "author": agent_name,
                "content":{
                    "parts": [
                        {
                            "text": f"Error {event_source.response.text}"
                        }
                    ]
                }
            }
            yield event
        else:
            async for server_event in event_source.aiter_sse():
                event = server_event.json()
                yield event

class QuizRequest(BaseModel):
    course_content: str

class AssessRequest(BaseModel):
    questions: list
    answers: list

class SimpleChatRequest(BaseModel):
    message: str
    user_id: str = "test_user"
    session_id: Optional[str] = None

@app.post("/api/chat_stream")
async def chat_stream(request: SimpleChatRequest):
    """Streaming chat endpoint."""
    global agent_name, agent_server_url
    if not agent_name:
        agent_name = (await list_agents(agent_server_url))[0] # type: ignore

    session = None
    if request.session_id:
        session = await get_session(
            agent_server_url, # type: ignore
            agent_name,
            request.user_id,
            request.session_id
        )
    if session is None:
        session = await create_session(
            agent_server_url, # type: ignore
            agent_name,
            request.user_id
        )

    events = query_adk_sever(
        agent_server_url, # type: ignore
        agent_name,
        request.user_id,
        request.message,
        session["id"]
    )

    async def event_generator():
        final_text = ""
        async for event in events:
            # Send progress updates based on which agent is active
            if event["author"] == "researcher":
                 yield json.dumps({"type": "progress", "text": "🔍 Researcher is gathering information..."}) + "\n"
            elif event["author"] == "judge":
                 yield json.dumps({"type": "progress", "text": "⚖️ Judge is evaluating findings..."}) + "\n"
            elif event["author"] == "content_builder":
                 yield json.dumps({"type": "progress", "text": "✍️ Content Builder is writing the course..."}) + "\n"
            # Accumulate final text
            if "content" in event and event["content"]:
                content = genai_types.Content.model_validate(event["content"])
                for part in content.parts: # type: ignore
                    if part.text:
                        final_text += part.text
        # Send final result
        yield json.dumps({"type": "result", "text": final_text.strip()}) + "\n"

    return StreamingResponse(event_generator(), media_type="application/x-ndjson")

async def _run_agent_and_collect_text(origin: str, app_name: str, message: str) -> str:
    """Creates a session, runs an agent via SSE, and collects all text output."""
    httpx_client = await get_client(origin)
    session_resp = await httpx_client.post(
        f"{origin}/apps/{app_name}/users/quiz_user/sessions",
        headers=[("Content-Type", "application/json")]
    )
    session_resp.raise_for_status()
    session_id = session_resp.json()["id"]

    request_body = {
        "appName": app_name,
        "userId": "quiz_user",
        "sessionId": session_id,
        "newMessage": {"role": "user", "parts": [{"text": message}]},
        "streaming": False
    }
    full_text = ""
    async with aconnect_sse(httpx_client, "POST", f"{origin}/run_sse", json=request_body) as es:
        if es.response.is_error:
            raise RuntimeError(f"Agent {app_name} returned {es.response.status_code}")
        async for ev in es.aiter_sse():
            event = ev.json()
            if "content" in event and event["content"]:
                content = genai_types.Content.model_validate(event["content"])
                for part in content.parts or []:
                    if part.text:
                        full_text += part.text
    return full_text


@app.post("/api/create_quiz")
async def create_quiz(request: QuizRequest):
    quizzer_url = os.getenv("QUIZZER_AGENT_CARD_URL", "http://localhost:8005/a2a/agent/.well-known/agent-card.json")
    quizzer_origin = quizzer_url.split("/a2a/")[0]
    full_text = await _run_agent_and_collect_text(
        quizzer_origin, "quizzer",
        f"Generate a quiz from this course content:\n\n{request.course_content}"
    )
    start = full_text.find("{")
    end = full_text.rfind("}") + 1
    if start != -1 and end > start:
        return json.loads(full_text[start:end])
    return {"questions": []}


@app.post("/api/assess_quiz")
async def assess_quiz(request: AssessRequest):
    assessor_url = os.getenv("ASSESSOR_AGENT_CARD_URL", "http://localhost:8006/a2a/agent/.well-known/agent-card.json")
    assessor_origin = assessor_url.split("/a2a/")[0]
    qa_text = "\n".join(
        f"Q{i+1}: {q['question']}\nCorrect: {q['correct']}\nUser answered: {request.answers[i] if i < len(request.answers) else 'Not answered'}"
        for i, q in enumerate(request.questions)
    )
    full_text = await _run_agent_and_collect_text(
        assessor_origin, "assessor",
        f"Please assess these quiz answers:\n\n{qa_text}"
    )
    start = full_text.find("{")
    end = full_text.rfind("}") + 1
    if start != -1 and end > start:
        return json.loads(full_text[start:end])
    return {"score": 0, "total": len(request.questions), "percentage": 0, "grade": "F", "feedback": "Could not assess.", "correct_answers": []}


# Mount frontend from the copied location
frontend_path = os.path.join(os.path.dirname(__file__), "frontend")
if os.path.exists(frontend_path):
    app.mount("/", StaticFiles(directory=frontend_path, html=True), name="frontend")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("PORT", 8000)))

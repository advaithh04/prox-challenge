"""
FastAPI Backend for Vulcan OmniPro 220 Welding Agent

This server provides the API endpoints for the multimodal welding assistant.
"""

import os
import json
import base64
from pathlib import Path
from typing import Optional
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, UploadFile, File, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from dotenv import load_dotenv

from welding_agent import WeldingAgent
from knowledge_extractor import KnowledgeExtractor, get_page_as_base64


# Load environment variables from parent directory
load_dotenv(Path(__file__).parent.parent / ".env")

# Initialize the agent
agent: Optional[WeldingAgent] = None
knowledge_base: Optional[dict] = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialize resources on startup."""
    global agent, knowledge_base

    # Check for API key (supports OpenRouter, Google, and Anthropic)
    openrouter_key = os.getenv("OPENROUTER_API_KEY")
    google_key = os.getenv("GOOGLE_API_KEY")
    anthropic_key = os.getenv("ANTHROPIC_API_KEY")

    if not openrouter_key and not google_key and not anthropic_key:
        print("WARNING: No API key set. Set OPENROUTER_API_KEY, GOOGLE_API_KEY, or ANTHROPIC_API_KEY.")
    else:
        try:
            agent = WeldingAgent()
            knowledge_base = agent.knowledge_base
            print("Welding Agent initialized successfully!")
        except Exception as e:
            print(f"ERROR initializing agent: {e}")

    yield

    # Cleanup (if needed)
    print("Shutting down...")


app = FastAPI(
    title="Vulcan OmniPro 220 Assistant",
    description="Multimodal AI assistant for the Vulcan OmniPro 220 welding system",
    version="1.0.0",
    lifespan=lifespan
)

# CORS middleware for frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, restrict this
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Serve static files (images from knowledge extraction)
knowledge_dir = Path(__file__).parent.parent / "knowledge"
if knowledge_dir.exists():
    app.mount("/knowledge", StaticFiles(directory=str(knowledge_dir)), name="knowledge")

# Serve product images
files_dir = Path(__file__).parent.parent
app.mount("/static", StaticFiles(directory=str(files_dir)), name="static")


# Request/Response Models
class ChatRequest(BaseModel):
    message: str
    include_images: bool = True


class ChatResponse(BaseModel):
    text: str
    artifacts: list
    images: list
    usage: dict


class ImageAnalysisRequest(BaseModel):
    image_base64: str
    media_type: str
    query: str


class PageRequest(BaseModel):
    document: str
    page: int


# API Endpoints
@app.get("/")
async def root():
    """Health check endpoint."""
    return {
        "status": "healthy",
        "service": "Vulcan OmniPro 220 Assistant",
        "agent_ready": agent is not None
    }


@app.get("/api/status")
async def get_status():
    """Get the current status of the agent."""
    return {
        "agent_ready": agent is not None,
        "knowledge_loaded": knowledge_base is not None,
        "documents_count": len(knowledge_base.get("documents", [])) if knowledge_base else 0,
        "sections_count": len(knowledge_base.get("sections", [])) if knowledge_base else 0,
        "images_count": len(knowledge_base.get("images", [])) if knowledge_base else 0
    }


@app.post("/api/chat", response_model=ChatResponse)
async def chat(request: ChatRequest):
    """Send a message to the welding agent."""
    if not agent:
        raise HTTPException(status_code=503, detail="Agent not initialized. Check API key.")

    try:
        response = agent.chat(request.message, include_images=request.include_images)

        # Don't include base64 images in the response (too large)
        images_info = []
        for img in response.get("images", []):
            images_info.append({
                "filename": img.get("filename"),
                "page": img.get("page"),
                "document": img.get("document"),
                "context": img.get("context", "")[:200]
            })

        return ChatResponse(
            text=response["text"],
            artifacts=response["artifacts"],
            images=images_info,
            usage=response["usage"]
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/chat/stream")
async def chat_stream(request: ChatRequest):
    """Stream a response from the welding agent."""
    if not agent:
        raise HTTPException(status_code=503, detail="Agent not initialized. Check API key.")

    async def generate():
        try:
            for chunk in agent.chat_stream(request.message, include_images=request.include_images):
                yield f"data: {json.dumps(chunk)}\n\n"
            yield "data: [DONE]\n\n"
        except Exception as e:
            yield f"data: {json.dumps({'type': 'error', 'content': str(e)})}\n\n"

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
        }
    )


@app.post("/api/analyze-image")
async def analyze_image(request: ImageAnalysisRequest):
    """Analyze a user-provided image."""
    if not agent:
        raise HTTPException(status_code=503, detail="Agent not initialized. Check API key.")

    try:
        response = agent.analyze_image(
            request.image_base64,
            request.media_type,
            request.query
        )
        return response

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/analyze-upload")
async def analyze_upload(
    file: UploadFile = File(...),
    query: str = Form(default="Please analyze this image related to my welding setup or results.")
):
    """Analyze an uploaded image file."""
    if not agent:
        raise HTTPException(status_code=503, detail="Agent not initialized. Check API key.")

    try:
        # Read and encode the file
        contents = await file.read()
        image_base64 = base64.b64encode(contents).decode("utf-8")

        # Determine media type
        media_type = file.content_type or "image/jpeg"

        response = agent.analyze_image(image_base64, media_type, query)
        return response

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/page/{document}/{page}")
async def get_page_image(document: str, page: int):
    """Get a rendered image of a specific page from a document."""
    if not agent:
        raise HTTPException(status_code=503, detail="Agent not initialized. Check API key.")

    result = agent.get_page_image(document, page)
    if not result:
        raise HTTPException(status_code=404, detail="Page not found")

    return result


@app.get("/api/documents")
async def list_documents():
    """List available documents."""
    if not knowledge_base:
        return {"documents": []}

    docs = []
    for doc in knowledge_base.get("documents", []):
        docs.append({
            "name": doc["name"],
            "title": doc["title"],
            "pages": len(doc.get("pages", []))
        })

    return {"documents": docs}


@app.get("/api/sections")
async def list_sections():
    """List all extracted sections."""
    if not knowledge_base:
        return {"sections": []}

    sections = []
    for section in knowledge_base.get("sections", []):
        sections.append({
            "title": section["title"],
            "document": section["document"],
            "keywords": section.get("keywords", [])
        })

    return {"sections": sections}


@app.get("/api/search")
async def search_knowledge(q: str):
    """Search the knowledge base."""
    if not knowledge_base:
        return {"results": []}

    q_lower = q.lower()
    results = []

    # Search sections
    for section in knowledge_base.get("sections", []):
        title = section.get("title", "")
        content = section.get("content", "")

        if q_lower in title.lower() or q_lower in content.lower():
            # Find the matching snippet
            content_lower = content.lower()
            idx = content_lower.find(q_lower)
            if idx >= 0:
                start = max(0, idx - 100)
                end = min(len(content), idx + 200)
                snippet = content[start:end]
            else:
                snippet = content[:200]

            results.append({
                "type": "section",
                "title": title,
                "document": section.get("document"),
                "snippet": f"...{snippet}...",
                "keywords": section.get("keywords", [])
            })

    return {"query": q, "results": results[:10]}


@app.post("/api/clear-history")
async def clear_history():
    """Clear the conversation history."""
    if agent:
        agent.clear_history()
    return {"status": "ok"}


@app.get("/api/suggested-questions")
async def get_suggested_questions():
    """Get a list of suggested questions to ask."""
    return {
        "questions": [
            {
                "category": "Setup",
                "questions": [
                    "How do I set up the machine for MIG welding?",
                    "What polarity do I need for TIG welding?",
                    "How do I configure the wire feed tensioner?",
                    "What's the proper grounding procedure?"
                ]
            },
            {
                "category": "Settings",
                "questions": [
                    "What's the duty cycle for MIG welding at 200A on 240V?",
                    "What wire speed should I use for 1/8 inch steel?",
                    "What voltage settings work for aluminum?",
                    "How do I adjust settings for flux-cored welding?"
                ]
            },
            {
                "category": "Troubleshooting",
                "questions": [
                    "I'm getting porosity in my welds. What should I check?",
                    "Why is my wire bird-nesting?",
                    "The arc keeps sputtering. What's wrong?",
                    "My welds have too much spatter. How do I fix this?"
                ]
            },
            {
                "category": "Processes",
                "questions": [
                    "What are the differences between MIG and flux-cored?",
                    "When should I use stick welding instead of MIG?",
                    "What shielding gas do I need for TIG welding steel?",
                    "Can I weld aluminum with this machine?"
                ]
            }
        ]
    }


# Run knowledge extraction if needed
@app.post("/api/extract-knowledge")
async def extract_knowledge():
    """Manually trigger knowledge extraction."""
    global knowledge_base

    try:
        extractor = KnowledgeExtractor(
            files_dir=str(Path(__file__).parent.parent / "files"),
            output_dir=str(knowledge_dir)
        )
        knowledge_base = extractor.extract_all()

        if agent:
            agent.knowledge_base = knowledge_base

        return {
            "status": "ok",
            "documents": len(knowledge_base.get("documents", [])),
            "sections": len(knowledge_base.get("sections", [])),
            "images": len(knowledge_base.get("images", []))
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)

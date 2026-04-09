"""
Vulcan OmniPro 220 Multimodal Reasoning Agent

This agent uses Claude or Gemini to answer technical questions about the Vulcan OmniPro 220
welding system with multimodal responses including diagrams, images, and
interactive artifacts.

Supports:
- OpenRouter (various models) - set OPENROUTER_API_KEY
- Google Gemini (FREE) - set GOOGLE_API_KEY
- Anthropic Claude (PAID) - set ANTHROPIC_API_KEY
"""

import json
import os
import re
from pathlib import Path
from typing import Optional, Generator
from knowledge_extractor import get_page_as_base64, KnowledgeExtractor

# System prompt for the welding agent
SYSTEM_PROMPT = """You are an expert technical assistant for the Vulcan OmniPro 220 multiprocess welding system sold by Harbor Freight. You have deep knowledge of:

- All four welding processes: MIG (GMAW), Flux-Cored (FCAW), TIG (GTAW), and Stick (SMAW)
- The machine's specifications, duty cycles, and operating parameters
- Setup procedures including polarity configuration for each process
- Wire feed mechanisms and tensioner calibrations
- Troubleshooting common welding problems
- Safety procedures and precautions

CRITICAL INSTRUCTIONS FOR RESPONSES:

1. **Be Technically Accurate**: Cross-reference multiple sections of the manual when needed. Always cite specific page numbers, specifications, and settings.

2. **Use Visual Responses**: When explaining complex concepts, you MUST generate interactive artifacts:
   - For polarity setups: Generate an SVG diagram showing exactly which cable goes where
   - For duty cycle questions: Generate an interactive calculator or table
   - For troubleshooting: Generate a flowchart or decision tree
   - For settings: Generate a configurator component

3. **Show Images When Relevant**: If the answer relates to something visual in the manual (wire feed mechanism, control panel, weld defects), explicitly reference and describe the relevant images.

4. **Clarify When Needed**: If a question is ambiguous, ask clarifying questions about:
   - Which welding process they're using
   - What material type and thickness
   - What their power source is (120V vs 240V)
   - What specific symptoms they're experiencing

5. **Think Like a Teacher**: The user is likely in their garage with the machine. Be patient, clear, and thorough. Use numbered steps for procedures.

ARTIFACT GENERATION FORMAT:
When generating interactive content, use this exact format:

```artifact
type: [react | svg | html]
title: [Descriptive title]
---
[Your code here]
```

Available artifact types:
- `react`: For interactive calculators, configurators, and dynamic content
- `svg`: For diagrams, schematics, and visual explanations
- `html`: For styled tables and static visual content

TECHNICAL SPECIFICATIONS YOU MUST KNOW:
- Input Power: 120V (15A min, 20A recommended) or 240V (30A)
- Output Range MIG: 30-220A
- Output Range TIG: 10-220A
- Output Range Stick: 20-170A
- Wire Sizes: 0.023", 0.030", 0.035", 0.045"
- Duty Cycle at 220A on 240V MIG: 25%
- Duty Cycle at 175A on 240V MIG: 40%
- Duty Cycle at 135A on 240V MIG: 60%

POLARITY SETTINGS:
- MIG (GMAW): DCEP (electrode positive) - Red cable to positive terminal
- Flux-Cored (FCAW) Self-Shielded: DCEN (electrode negative) - Red cable to negative terminal
- Flux-Cored (FCAW) Gas-Shielded: DCEP (electrode positive) - Red cable to positive terminal
- TIG (GTAW): DCEN (electrode negative) - Torch to negative terminal, work clamp to positive
- Stick (SMAW): Depends on electrode type - typically DCEP for most rods

Always be helpful, accurate, and safety-conscious. If something could be dangerous, warn the user clearly."""


class WeldingAgent:
    """
    Multimodal reasoning agent for the Vulcan OmniPro 220 welding system.
    Supports OpenRouter, Google Gemini, and Anthropic Claude.
    """

    def __init__(self, api_key: Optional[str] = None, provider: Optional[str] = None):
        # Determine which API to use
        self.openrouter_api_key = os.getenv("OPENROUTER_API_KEY")
        self.google_api_key = os.getenv("GOOGLE_API_KEY")
        self.anthropic_api_key = api_key or os.getenv("ANTHROPIC_API_KEY")

        # Auto-detect provider based on available keys (OpenRouter first)
        if provider:
            self.provider = provider
        elif self.openrouter_api_key:
            self.provider = "openrouter"
        elif self.google_api_key:
            self.provider = "gemini"
        elif self.anthropic_api_key:
            self.provider = "anthropic"
        else:
            raise ValueError("OPENROUTER_API_KEY, GOOGLE_API_KEY, or ANTHROPIC_API_KEY is required")

        # Initialize the appropriate client
        if self.provider == "openrouter":
            from openai import OpenAI
            self.client = OpenAI(
                base_url="https://openrouter.ai/api/v1",
                api_key=self.openrouter_api_key
            )
            self.model_name = "anthropic/claude-3.5-sonnet"
            self.model = None
            print(f"Using OpenRouter with {self.model_name}")
        elif self.provider == "gemini":
            import google.generativeai as genai
            genai.configure(api_key=self.google_api_key)
            self.model = genai.GenerativeModel(
                model_name="gemini-2.0-flash",
                system_instruction=SYSTEM_PROMPT
            )
            self.client = None
            print(f"Using Google Gemini (FREE)")
        else:
            import anthropic
            self.client = anthropic.Anthropic(api_key=self.anthropic_api_key)
            self.model_name = "claude-sonnet-4-20250514"
            self.model = None
            print(f"Using Anthropic Claude (PAID)")

        # Load knowledge base
        self.knowledge_dir = Path(__file__).parent.parent / "knowledge"
        self.files_dir = Path(__file__).parent.parent / "files"
        self.knowledge_base = self._load_knowledge_base()

        # Conversation history
        self.conversation_history = []
        self.gemini_chat = None

    def _load_knowledge_base(self) -> dict:
        """Load the extracted knowledge base."""
        index_path = self.knowledge_dir / "knowledge_index.json"

        if not index_path.exists():
            print("Knowledge base not found. Running extraction...")
            extractor = KnowledgeExtractor(
                files_dir=str(self.files_dir),
                output_dir=str(self.knowledge_dir)
            )
            return extractor.extract_all()

        with open(index_path, "r") as f:
            return json.load(f)

    def _get_relevant_context(self, query: str) -> str:
        """Get relevant sections from the knowledge base for a query."""
        query_lower = query.lower()
        relevant_sections = []

        keyword_sections = {
            "duty cycle": ["DUTY CYCLE", "SPECIFICATIONS", "RATING"],
            "mig": ["MIG", "GMAW", "GAS METAL ARC"],
            "tig": ["TIG", "GTAW", "GAS TUNGSTEN"],
            "flux": ["FLUX", "FCAW", "FLUX-CORED"],
            "stick": ["STICK", "SMAW", "SHIELDED METAL ARC"],
            "polarity": ["POLARITY", "DCEP", "DCEN", "CONNECTION"],
            "wire": ["WIRE", "FEED", "DRIVE ROLL", "TENSIONER"],
            "troubleshoot": ["TROUBLESHOOT", "PROBLEM", "SOLUTION"],
            "porosity": ["POROSITY", "DEFECT", "WELD QUALITY"],
            "spatter": ["SPATTER", "DEFECT"],
            "setup": ["SETUP", "INSTALLATION", "ASSEMBLY"],
            "safety": ["SAFETY", "WARNING", "CAUTION"],
            "voltage": ["VOLTAGE", "SETTINGS", "PARAMETERS"],
            "amperage": ["AMPERAGE", "CURRENT", "SETTINGS"],
            "gas": ["GAS", "SHIELDING", "ARGON", "CO2"],
            "ground": ["GROUND", "WORK CLAMP", "EARTH"]
        }

        relevant_keywords = []
        for keyword, sections in keyword_sections.items():
            if keyword in query_lower:
                relevant_keywords.extend(sections)

        for section in self.knowledge_base.get("sections", []):
            title_upper = section.get("title", "").upper()
            content_lower = section.get("content", "").lower()

            if any(kw in title_upper for kw in relevant_keywords):
                relevant_sections.append(section)
            elif any(kw.lower() in content_lower for kw in relevant_keywords):
                relevant_sections.append(section)

        context_parts = []
        for section in relevant_sections[:5]:
            context_parts.append(f"=== {section['title']} ===\n{section['content'][:2000]}")

        return "\n\n".join(context_parts)

    def _get_relevant_images(self, query: str) -> list:
        """Get relevant images from the knowledge base."""
        query_lower = query.lower()
        relevant_images = []

        image_keywords = {
            "panel": ["panel", "control", "display", "front"],
            "wire": ["wire", "feed", "drive", "roll", "spool"],
            "polarity": ["polarity", "terminal", "connection", "cable"],
            "weld": ["weld", "bead", "defect", "porosity", "quality"],
            "diagram": ["diagram", "schematic", "wiring"],
            "torch": ["torch", "gun", "tig", "mig"]
        }

        for keyword, terms in image_keywords.items():
            if any(term in query_lower for term in terms):
                for img in self.knowledge_base.get("images", []):
                    context = img.get("context", "").lower()
                    if any(term in context for term in terms):
                        relevant_images.append(img)

        return relevant_images[:3]

    def chat(self, query: str, include_images: bool = True) -> dict:
        """Send a query to the agent and get a response."""
        context = self._get_relevant_context(query)

        query_with_context = f"""User Question: {query}

Relevant Documentation:
{context}

Please provide a comprehensive answer. If visual explanation would help, generate an appropriate artifact (SVG diagram, React component, or HTML table). Always cite specific settings, specifications, or page references when applicable."""

        if self.provider == "openrouter":
            return self._chat_openrouter(query_with_context, query)
        elif self.provider == "gemini":
            return self._chat_gemini(query_with_context, query)
        else:
            return self._chat_anthropic(query_with_context, query, include_images)

    def _chat_openrouter(self, query_with_context: str, original_query: str) -> dict:
        """Chat using OpenRouter."""
        messages = [{"role": "system", "content": SYSTEM_PROMPT}]
        messages.extend(self.conversation_history)
        messages.append({"role": "user", "content": query_with_context})

        response = self.client.chat.completions.create(
            model=self.model_name,
            max_tokens=4096,
            messages=messages
        )

        response_text = response.choices[0].message.content
        artifacts = self._parse_artifacts(response_text)

        self.conversation_history.append({"role": "user", "content": original_query})
        self.conversation_history.append({"role": "assistant", "content": response_text})

        if len(self.conversation_history) > 20:
            self.conversation_history = self.conversation_history[-20:]

        return {
            "text": response_text,
            "artifacts": artifacts,
            "images": self._get_relevant_images(original_query),
            "usage": {
                "input_tokens": response.usage.prompt_tokens if response.usage else 0,
                "output_tokens": response.usage.completion_tokens if response.usage else 0
            }
        }

    def _chat_gemini(self, query_with_context: str, original_query: str) -> dict:
        """Chat using Google Gemini."""
        import google.generativeai as genai

        # Start or continue chat
        if self.gemini_chat is None:
            self.gemini_chat = self.model.start_chat(history=[])

        response = self.gemini_chat.send_message(query_with_context)
        response_text = response.text

        # Parse artifacts
        artifacts = self._parse_artifacts(response_text)

        # Update history
        self.conversation_history.append({"role": "user", "content": original_query})
        self.conversation_history.append({"role": "assistant", "content": response_text})

        if len(self.conversation_history) > 20:
            self.conversation_history = self.conversation_history[-20:]

        return {
            "text": response_text,
            "artifacts": artifacts,
            "images": self._get_relevant_images(original_query),
            "usage": {"input_tokens": 0, "output_tokens": 0}  # Gemini doesn't expose this easily
        }

    def _chat_anthropic(self, query_with_context: str, original_query: str, include_images: bool) -> dict:
        """Chat using Anthropic Claude."""
        content = [{"type": "text", "text": query_with_context}]

        if include_images:
            relevant_images = self._get_relevant_images(original_query)
            for img in relevant_images:
                if img.get("base64"):
                    content.append({
                        "type": "image",
                        "source": {
                            "type": "base64",
                            "media_type": img.get("media_type", "image/png"),
                            "data": img["base64"]
                        }
                    })

        messages = list(self.conversation_history)
        messages.append({"role": "user", "content": content if len(content) > 1 else query_with_context})

        response = self.client.messages.create(
            model=self.model_name,
            max_tokens=4096,
            system=SYSTEM_PROMPT,
            messages=messages
        )

        response_text = ""
        for block in response.content:
            if block.type == "text":
                response_text += block.text

        artifacts = self._parse_artifacts(response_text)

        self.conversation_history.append({"role": "user", "content": original_query})
        self.conversation_history.append({"role": "assistant", "content": response_text})

        if len(self.conversation_history) > 20:
            self.conversation_history = self.conversation_history[-20:]

        return {
            "text": response_text,
            "artifacts": artifacts,
            "images": self._get_relevant_images(original_query),
            "usage": {
                "input_tokens": response.usage.input_tokens,
                "output_tokens": response.usage.output_tokens
            }
        }

    def chat_stream(self, query: str, include_images: bool = True) -> Generator:
        """Stream a response from the agent."""
        context = self._get_relevant_context(query)

        query_with_context = f"""User Question: {query}

Relevant Documentation:
{context}

Please provide a comprehensive answer. If visual explanation would help, generate an appropriate artifact (SVG diagram, React component, or HTML table). Always cite specific settings, specifications, or page references when applicable."""

        if self.provider == "openrouter":
            yield from self._stream_openrouter(query_with_context, query)
        elif self.provider == "gemini":
            yield from self._stream_gemini(query_with_context, query)
        else:
            yield from self._stream_anthropic(query_with_context, query, include_images)

    def _stream_openrouter(self, query_with_context: str, original_query: str) -> Generator:
        """Stream using OpenRouter."""
        messages = [{"role": "system", "content": SYSTEM_PROMPT}]
        messages.extend(self.conversation_history)
        messages.append({"role": "user", "content": query_with_context})

        stream = self.client.chat.completions.create(
            model=self.model_name,
            max_tokens=4096,
            messages=messages,
            stream=True
        )

        full_response = ""
        for chunk in stream:
            if chunk.choices and chunk.choices[0].delta.content:
                text = chunk.choices[0].delta.content
                full_response += text
                yield {"type": "text", "content": text}

        artifacts = self._parse_artifacts(full_response)
        if artifacts:
            yield {"type": "artifacts", "content": artifacts}

        self.conversation_history.append({"role": "user", "content": original_query})
        self.conversation_history.append({"role": "assistant", "content": full_response})

    def _stream_gemini(self, query_with_context: str, original_query: str) -> Generator:
        """Stream using Google Gemini."""
        if self.gemini_chat is None:
            self.gemini_chat = self.model.start_chat(history=[])

        response = self.gemini_chat.send_message(query_with_context, stream=True)

        full_response = ""
        for chunk in response:
            if chunk.text:
                full_response += chunk.text
                yield {"type": "text", "content": chunk.text}

        artifacts = self._parse_artifacts(full_response)
        if artifacts:
            yield {"type": "artifacts", "content": artifacts}

        self.conversation_history.append({"role": "user", "content": original_query})
        self.conversation_history.append({"role": "assistant", "content": full_response})

    def _stream_anthropic(self, query_with_context: str, original_query: str, include_images: bool) -> Generator:
        """Stream using Anthropic Claude."""
        content = [{"type": "text", "text": query_with_context}]

        if include_images:
            relevant_images = self._get_relevant_images(original_query)
            for img in relevant_images:
                if img.get("base64"):
                    content.append({
                        "type": "image",
                        "source": {
                            "type": "base64",
                            "media_type": img.get("media_type", "image/png"),
                            "data": img["base64"]
                        }
                    })

        messages = list(self.conversation_history)
        messages.append({"role": "user", "content": content if len(content) > 1 else query_with_context})

        with self.client.messages.stream(
            model=self.model_name,
            max_tokens=4096,
            system=SYSTEM_PROMPT,
            messages=messages
        ) as stream:
            full_response = ""
            for text in stream.text_stream:
                full_response += text
                yield {"type": "text", "content": text}

            artifacts = self._parse_artifacts(full_response)
            if artifacts:
                yield {"type": "artifacts", "content": artifacts}

            self.conversation_history.append({"role": "user", "content": original_query})
            self.conversation_history.append({"role": "assistant", "content": full_response})

    def _parse_artifacts(self, text: str) -> list:
        """Parse artifacts from the response text."""
        artifacts = []
        artifact_pattern = r"```artifact\ntype:\s*(\w+)\ntitle:\s*([^\n]+)\n---\n([\s\S]*?)```"
        matches = re.findall(artifact_pattern, text)

        for match in matches:
            artifact_type, title, code = match
            artifacts.append({
                "type": artifact_type.strip(),
                "title": title.strip(),
                "code": code.strip()
            })

        return artifacts

    def get_page_image(self, document: str, page: int) -> Optional[dict]:
        """Get a rendered image of a specific page from a document."""
        pdf_files = {
            "owner-manual": "owner-manual.pdf",
            "quick-start-guide": "quick-start-guide.pdf",
            "selection-chart": "selection-chart.pdf"
        }

        pdf_filename = pdf_files.get(document)
        if not pdf_filename:
            return None

        pdf_path = self.files_dir / pdf_filename
        if not pdf_path.exists():
            return None

        return get_page_as_base64(str(pdf_path), page - 1)

    def clear_history(self):
        """Clear the conversation history."""
        self.conversation_history = []
        self.gemini_chat = None

    def analyze_image(self, image_base64: str, media_type: str, query: str) -> dict:
        """Analyze a user-provided image."""
        prompt = f"""The user has shared an image related to their Vulcan OmniPro 220 welding setup or results.

User's question/context: {query}

Please analyze the image and provide helpful feedback. If it's a weld, identify any defects and suggest improvements. If it's the machine setup, verify if it's correct for their intended welding process."""

        if self.provider == "openrouter":
            messages = [
                {"role": "system", "content": SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": [
                        {"type": "image_url", "image_url": {"url": f"data:{media_type};base64,{image_base64}"}},
                        {"type": "text", "text": prompt}
                    ]
                }
            ]
            response = self.client.chat.completions.create(
                model=self.model_name,
                max_tokens=2048,
                messages=messages
            )
            response_text = response.choices[0].message.content
        elif self.provider == "gemini":
            import google.generativeai as genai
            import base64

            # Decode base64 to bytes
            image_bytes = base64.b64decode(image_base64)

            # Create image part for Gemini
            image_part = {
                "mime_type": media_type,
                "data": image_bytes
            }

            response = self.model.generate_content([prompt, image_part])
            response_text = response.text
        else:
            content = [
                {
                    "type": "image",
                    "source": {
                        "type": "base64",
                        "media_type": media_type,
                        "data": image_base64
                    }
                },
                {"type": "text", "text": prompt}
            ]

            response = self.client.messages.create(
                model=self.model_name,
                max_tokens=2048,
                system=SYSTEM_PROMPT,
                messages=[{"role": "user", "content": content}]
            )

            response_text = ""
            for block in response.content:
                if block.type == "text":
                    response_text += block.text

        return {
            "text": response_text,
            "artifacts": self._parse_artifacts(response_text)
        }


# Example usage and testing
if __name__ == "__main__":
    from dotenv import load_dotenv
    load_dotenv()

    agent = WeldingAgent()

    test_queries = [
        "What's the duty cycle for MIG welding at 200A on 240V?",
        "What polarity setup do I need for TIG welding?",
        "I'm getting porosity in my flux-cored welds. What should I check?"
    ]

    for query in test_queries:
        print(f"\n{'='*60}")
        print(f"Query: {query}")
        print("=" * 60)

        response = agent.chat(query)
        print(f"\nResponse:\n{response['text'][:1000]}...")

        if response["artifacts"]:
            print(f"\nArtifacts generated: {len(response['artifacts'])}")
            for artifact in response["artifacts"]:
                print(f"  - {artifact['type']}: {artifact['title']}")

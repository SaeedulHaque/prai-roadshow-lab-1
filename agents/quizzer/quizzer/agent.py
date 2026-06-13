from google.adk.agents import Agent

MODEL = "gemini-3-flash-preview"

quizzer = Agent(
    name="quizzer",
    model=MODEL,
    description="Generates a multiple-choice quiz from course content.",
    instruction="""
    You are a quiz creator. Given course content, generate exactly 5 multiple-choice questions.
    Each question must have 4 options (A, B, C, D) and one correct answer.

    Respond ONLY with a valid JSON object in this exact format:
    {
      "questions": [
        {
          "question": "...",
          "options": ["A) ...", "B) ...", "C) ...", "D) ..."],
          "correct": "A) ..."
        }
      ]
    }

    Do not include any text outside the JSON.
    """,
)

root_agent = quizzer

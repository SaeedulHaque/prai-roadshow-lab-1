from google.adk.agents import Agent
from pydantic import BaseModel, Field

MODEL = "gemini-3-flash-preview"


class AssessmentResult(BaseModel):
    score: int = Field(description="Number of correct answers")
    total: int = Field(description="Total number of questions")
    percentage: float = Field(description="Score as a percentage")
    grade: str = Field(description="Letter grade: A, B, C, D, or F")
    feedback: str = Field(description="Encouraging, personalized feedback based on performance")
    correct_answers: list[str] = Field(description="List of correct answers for each question")


assessor = Agent(
    name="assessor",
    model=MODEL,
    description="Assesses quiz answers and provides scored feedback.",
    instruction="""
    You are a fair and encouraging assessor. You will receive:
    - A list of quiz questions with correct answers
    - The user's submitted answers

    Grade the quiz and provide:
    - The score (correct count out of total)
    - A percentage
    - A letter grade (A: 90-100%, B: 80-89%, C: 70-79%, D: 60-69%, F: <60%)
    - Warm, specific feedback mentioning what they did well and where to improve
    - The list of correct answers

    Be encouraging regardless of score.
    """,
    output_schema=AssessmentResult,
    disallow_transfer_to_parent=True,
    disallow_transfer_to_peers=True,
)

root_agent = assessor

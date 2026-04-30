"""routers/qa.py — §12 Product Q&A."""

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException

from app.core.auth import get_current_user
from app.core.messages import ErrorMessages
from app.db.surreal import DB, get_db
from app.models.review import AnswerCreate, QuestionCreate

router = APIRouter()
_NOW = lambda: datetime.now(timezone.utc).isoformat()  # noqa: E731


@router.post("/products/{product_id}/questions", status_code=201)
async def ask_question(
    product_id: str, data: QuestionCreate,
    db: DB = Depends(get_db), _user: dict = Depends(get_current_user),
):
    p = await db.select_one("product", product_id)
    if not p:
        raise HTTPException(404, ErrorMessages.PRODUCT_NOT_FOUND.value)
    record = await db.create(
        "question",
        {
            "product_id": product_id,
            "user_id": _user["id"],
            "question": data.question,
            "helpful_count": 0,
            "created_at": _NOW(),
        },
    )
    return record


@router.get("/products/{product_id}/questions")
async def list_questions(product_id: str, db: DB = Depends(get_db)):
    questions = await db.query(
        "SELECT * FROM question WHERE product_id = $pid ORDER BY created_at DESC",
        {"pid": product_id},
    )
    for q in questions:
        q_id = str(q["id"]).split(":")[-1]
        q["answers"] = await db.query(
            "SELECT * FROM answer WHERE question_id = $qid ORDER BY created_at ASC",
            {"qid": q_id},
        )
    return questions


@router.post("/questions/{question_id}/answers", status_code=201)
async def post_answer(
    question_id: str, data: AnswerCreate,
    db: DB = Depends(get_db), _user: dict = Depends(get_current_user),
):
    q = await db.select_one("question", question_id)
    if not q:
        raise HTTPException(404, ErrorMessages.QUESTION_NOT_FOUND.value)
    record = await db.create(
        "answer",
        {
            "question_id": question_id,
            "user_id": _user["id"],
            "answer": data.answer,
            "answered_by": data.answered_by,
            "created_at": _NOW(),
        },
    )
    return record


@router.delete("/questions/{question_id}", status_code=204)
async def delete_question(
    question_id: str,
    db: DB = Depends(get_db), _user: dict = Depends(get_current_user),
):
    q = await db.select_one("question", question_id)
    if not q:
        raise HTTPException(404, ErrorMessages.QUESTION_NOT_FOUND.value)
    if q["user_id"] != _user["id"] and _user.get("role") != "admin":
        raise HTTPException(403, ErrorMessages.FORBIDDEN.value)
    await db.delete("question", question_id)
    await db.query("DELETE answer WHERE question_id = $qid", {"qid": question_id})


@router.post("/questions/{question_id}/helpful")
async def mark_question_helpful(question_id: str, db: DB = Depends(get_db)):
    q = await db.select_one("question", question_id)
    if not q:
        raise HTTPException(404, ErrorMessages.QUESTION_NOT_FOUND.value)
    count = q.get("helpful_count", 0) + 1
    await db.update("question", question_id, {"helpful_count": count})
    return {"helpful_count": count}

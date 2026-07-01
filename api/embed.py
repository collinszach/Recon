"""Semantic embedding client + near-duplicate detection for the roles feed.

Calls the Ollama OpenAI-compatible /v1/embeddings endpoint on gs65.
All public functions no-op safely when embed_enabled=False or gs65 is down.
"""
import logging
import httpx
from sqlalchemy import text
from sqlalchemy.orm import Session
from config import settings

log = logging.getLogger("recon.embed")


def _role_text(title: str, company: str | None, description: str | None) -> str:
    """Compact text that captures the discriminating features of a role."""
    parts = [title]
    if company:
        parts.append(company)
    if description:
        parts.append(description[:500])
    return " | ".join(parts)


def _embed_texts(texts: list[str]) -> list[list[float] | None]:
    """Call Ollama /v1/embeddings. Returns one vector per input; None on error."""
    results: list[list[float] | None] = [None] * len(texts)
    batch_size = settings.embed_batch_size
    for i in range(0, len(texts), batch_size):
        batch = texts[i : i + batch_size]
        try:
            resp = httpx.post(
                f"{settings.embed_base_url}/embeddings",
                json={"model": settings.embed_model, "input": batch},
                timeout=120.0,
            )
            resp.raise_for_status()
            for item in resp.json()["data"]:
                results[i + item["index"]] = item["embedding"]
        except Exception as e:
            log.warning("embed batch %d–%d failed: %s", i, i + batch_size, e)
    return results


def embed_and_dedup(db: Session, roles: list) -> dict:
    """Embed a list of Role ORM objects, persist embeddings, and mark near-dups.

    Near-dup rule: a JSearch/USAJobs role whose cosine similarity to any ATS
    role at the same company exceeds embed_dedup_threshold gets is_duplicate=True
    and won't appear in the feed.  ATS roles are always canonical.

    Returns {"embedded": n, "duplicates": n}.
    """
    if not settings.embed_enabled or not roles:
        return {"embedded": 0, "duplicates": 0}

    texts = [
        _role_text(r.title, r.company.name if r.company else None, r.description)
        for r in roles
    ]
    vectors = _embed_texts(texts)

    embedded, duplicates = 0, 0
    for role, vec in zip(roles, vectors):
        if vec is None:
            continue
        role.embedding = vec
        embedded += 1

        # Only non-ATS roles can be duplicates (ATS is canonical).
        if (role.source or "ats") == "ats" or not role.company_id:
            continue

        # pgvector cosine distance: 1 - (a <=> b) gives similarity in [0,1].
        # Use a parameterised cast so psycopg passes the list as a vector literal.
        row = db.execute(
            text("""
                SELECT id, 1 - (embedding <=> CAST(:emb AS vector)) AS sim
                FROM   roles
                WHERE  company_id  = :co_id
                  AND  source      = 'ats'
                  AND  embedding   IS NOT NULL
                  AND  status      IN ('open', 'changed')
                  AND  id         != :rid
                ORDER  BY sim DESC
                LIMIT  1
            """),
            {
                "emb": "[" + ",".join(f"{v:.8f}" for v in vec) + "]",
                "co_id": role.company_id,
                "rid": role.id,
            },
        ).fetchone()

        if row and row.sim >= settings.embed_dedup_threshold:
            role.is_duplicate = True
            duplicates += 1
            log.info(
                "dedup: role %d (%s) is near-dup of %d (sim=%.3f)",
                role.id, role.title, row.id, row.sim,
            )

    db.commit()
    log.info("embed_and_dedup: %d embedded, %d duplicates", embedded, duplicates)
    return {"embedded": embedded, "duplicates": duplicates}


def backfill(db: Session, limit: int = 200) -> dict:
    """Embed open roles that have no embedding yet, in score-order.

    Call repeatedly (via the /api/admin/backfill-embeddings endpoint) until
    the response shows embedded=0, which means the backfill is complete.
    """
    from db import Role
    from sqlalchemy import select

    roles = (
        db.scalars(
            select(Role)
            .where(Role.status.in_(["open", "changed"]))
            .where(Role.embedding.is_(None))
            .order_by(Role.fit_score.desc().nullslast(), Role.id.desc())
            .limit(limit)
        )
        .all()
    )
    if not roles:
        return {"embedded": 0, "duplicates": 0, "remaining": 0}

    result = embed_and_dedup(db, roles)

    remaining = db.scalar(
        text("SELECT COUNT(*) FROM roles WHERE status IN ('open','changed') AND embedding IS NULL")
    )
    result["remaining"] = remaining or 0
    return result

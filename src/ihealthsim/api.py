from __future__ import annotations

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from .scoring import OnlineScorer


class FeatureVectorIn(BaseModel):
    asset_id: str = Field(..., examples=["PUMP-001"])
    features: dict[str, float]


def create_app(scorer: OnlineScorer) -> FastAPI:
    app = FastAPI(title="Industrial Health Sim API")

    @app.get("/health/{asset_id}")
    def get_health(asset_id: str):
        hr = scorer.latest(asset_id)
        if hr is None:
            raise HTTPException(status_code=404, detail="no health result yet")
        return hr.__dict__

    @app.post("/predict_features")
    def predict_features(body: FeatureVectorIn):
        # 将输入特征对齐模型特征列
        import numpy as np
        import pandas as pd

        row = {c: body.features.get(c, np.nan) for c in scorer.feature_cols}
        x = pd.DataFrame([row])
        proba = scorer.pipe.predict_proba(x)[0].tolist()
        level = int(scorer.pipe.predict(x)[0])
        explanation = scorer._explain_path(x)
        score = float(100.0 - (level / 3.0) * 100.0)
        return {
            "asset_id": body.asset_id,
            "health_level": level,
            "health_score": score,
            "proba": proba,
            "explanation": explanation,
        }

    return app

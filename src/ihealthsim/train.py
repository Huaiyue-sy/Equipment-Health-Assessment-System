from __future__ import annotations

import os
from dataclasses import dataclass

import joblib
import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.impute import SimpleImputer
from sklearn.metrics import classification_report
from sklearn.pipeline import Pipeline
from sklearn.tree import DecisionTreeClassifier


@dataclass(frozen=True)
class TrainConfig:
    max_depth: int = 5
    min_samples_leaf: int = 50
    test_size: float = 0.3
    random_state: int = 42
    feature_set: str = "online"  # "online" | "all"
    model_type: str = "tree"  # "tree" | "xgb" | "lgb"


# 需与 OnlineScorer 里实时计算的特征保持一致
ONLINE_FEATURE_COLS: list[str] = [
    "rpm_mean",
    "load_mean",
    "vib_rms_mean",
    "temp_c_mean",
    "motor_current_a_mean",
    "vib_rms_std",
    "temp_c_std",
    "vib_rms_norm",
]


def _make_classifier(cfg: TrainConfig):
    """根据 model_type 创建分类器。"""
    if cfg.model_type == "tree":
        return DecisionTreeClassifier(
            max_depth=cfg.max_depth,
            min_samples_leaf=cfg.min_samples_leaf,
            class_weight="balanced",
            random_state=cfg.random_state,
        )
    elif cfg.model_type == "xgb":
        from xgboost import XGBClassifier
        return XGBClassifier(
            max_depth=cfg.max_depth,
            learning_rate=0.1,
            n_estimators=100,
            subsample=0.8,
            colsample_bytree=0.8,
            eval_metric="mlogloss",
            random_state=cfg.random_state,
        )
    elif cfg.model_type == "lgb":
        from lightgbm import LGBMClassifier
        return LGBMClassifier(
            max_depth=cfg.max_depth,
            learning_rate=0.1,
            n_estimators=100,
            subsample=0.8,
            colsample_bytree=0.8,
            min_child_samples=cfg.min_samples_leaf,
            class_weight="balanced",
            random_state=cfg.random_state,
            verbose=-1,
        )
    else:
        raise ValueError(f"不支持的 model_type: {cfg.model_type}，可选 tree/xgb/lgb")


def train_tree(features_csv: str, model_out: str, *, cfg: TrainConfig = TrainConfig()) -> str:
    os.makedirs(os.path.dirname(model_out), exist_ok=True)

    df = pd.read_csv(features_csv)

    # 训练特征：排除索引类字段与标签
    drop_cols = {"asset_id", "window_start_ms", "y"}
    all_feature_cols = [c for c in df.columns if c not in drop_cols]

    if cfg.feature_set == "online":
        missing = [c for c in ONLINE_FEATURE_COLS if c not in all_feature_cols]
        if missing:
            raise ValueError(
                "features.csv 缺少在线特征列，无法用 feature_set=online 训练：" + ", ".join(missing)
            )
        feature_cols = [c for c in ONLINE_FEATURE_COLS if c in all_feature_cols]
    elif cfg.feature_set == "all":
        feature_cols = all_feature_cols
    else:
        raise ValueError("feature_set 仅支持 'online' 或 'all'")

    X = df[feature_cols]
    y = df["y"].astype(int)

    print("=== Label distribution (y) ===")
    print(y.value_counts().sort_index())

    # 时间序列按时间切分：每个 asset 各自按 window_start_ms 排序后切分，再合并
    if "window_start_ms" in df.columns:
        df = df.sort_values(["asset_id", "window_start_ms"])
    else:
        print("[WARNING] features.csv 缺少 window_start_ms，将保持原始顺序切分")

    # 对每个设备单独做时间切分
    train_parts = []
    test_parts = []
    for asset_id, group in df.groupby("asset_id", sort=False):
        group = group.sort_values("window_start_ms")
        n = len(group)
        split_idx = int(n * (1 - cfg.test_size))
        if split_idx == 0:
            split_idx = 1
        if split_idx >= n:
            split_idx = n - 1
        train_parts.append(group.iloc[:split_idx])
        test_parts.append(group.iloc[split_idx:])

    train_df = pd.concat(train_parts, ignore_index=True)
    test_df = pd.concat(test_parts, ignore_index=True)

    X_train = train_df[feature_cols]
    y_train = train_df["y"].astype(int)
    X_test = test_df[feature_cols]
    y_test = test_df["y"].astype(int)

    print(f"Train: {len(X_train)} 个窗口 ({len(train_parts)} 设备)")
    print(f"Test:  {len(X_test)} 个窗口 ({len(test_parts)} 设备)")
    print(f"Train label dist: {dict(y_train.value_counts().sort_index())}")
    print(f"Test  label dist: {dict(y_test.value_counts().sort_index())}")

    numeric_features = list(X.columns)
    pre = ColumnTransformer(
        transformers=[
            ("num", SimpleImputer(strategy="median"), numeric_features),
        ],
        remainder="drop",
    )

    clf = _make_classifier(cfg)

    pipe = Pipeline([("pre", pre), ("clf", clf)])
    pipe.fit(X_train, y_train)

    y_pred = pipe.predict(X_test)
    report = classification_report(y_test, y_pred, digits=3)

    # 特征重要性（仅 tree/xgb/lgb 支持）
    feature_importance = None
    try:
        if cfg.model_type in ("xgb", "lgb"):
            fi = clf.feature_importances_
        else:
            fi = clf.feature_importances_
        pairs = sorted(zip(feature_cols, fi), key=lambda x: x[1], reverse=True)
        feature_importance = [[f, float(v)] for f, v in pairs]
    except Exception:
        pass

    bundle = {
        "pipeline": pipe,
        "feature_cols": feature_cols,
        "report": report,
        "config": cfg,
        "model_type": cfg.model_type,
        "feature_importance": feature_importance,
    }
    joblib.dump(bundle, model_out)

    model_name = {"tree": "Decision Tree", "xgb": "XGBoost", "lgb": "LightGBM"}[cfg.model_type]
    print(f"=== {model_name} validation report ===")
    print(report)
    if feature_importance:
        print("=== Feature Importance ===")
        for name, imp in feature_importance[:10]:
            print(f"  {name}: {imp:.4f}")
    return model_out

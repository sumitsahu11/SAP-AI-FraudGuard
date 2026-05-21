import pandas as pd
from sklearn.ensemble import RandomForestClassifier
from sklearn.preprocessing import OneHotEncoder
from sklearn.compose import ColumnTransformer
from sklearn.pipeline import Pipeline

def train_classifier(df: pd.DataFrame):
    target = "IsFraudLabel"

    features = [
        "Amount",
        "VendorInvoiceCount",
        "DaysSinceLastInvoice",
        "HighValueInvoice",
        "HasPO",
        "Vendor"
    ]

    X = df[features]
    y = df[target]

    numeric_features = [
        "Amount",
        "VendorInvoiceCount",
        "DaysSinceLastInvoice"
    ]
    categorical_features = ["Vendor"]

    preprocessor = ColumnTransformer(
        transformers=[
            ("num", "passthrough", numeric_features),
            ("cat", OneHotEncoder(handle_unknown="ignore"), categorical_features)
        ]
    )

    model = RandomForestClassifier(
        n_estimators=200,
        max_depth=8,
        random_state=42
    )

    pipe = Pipeline(steps=[
        ("prep", preprocessor),
        ("model", model)
    ])

    pipe.fit(X, y)
    return pipe
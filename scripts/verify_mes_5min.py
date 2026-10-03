"""验证 5min Qlib 数据能加载，并覆盖交易时间段"""
from pathlib import Path
import qlib
from qlib.data import D
from qlib.config import C

ROOT = Path(__file__).resolve().parent.parent
QLIB_DIR = ROOT / "data" / "qlib_data"

qlib.init(
    provider_uri={
        "5min": str(QLIB_DIR / "futures_5min"),
        "15min": str(QLIB_DIR / "futures_15min"),
        "60min": str(QLIB_DIR / "futures_60min"),
    },
    region="us",
)
C.joblib_backend = "threading"

instruments = D.instruments("all")
df = D.features(instruments, ["$close", "$volume"], freq="5min")
print("Loaded features:")
print(df.tail())
print("\nShape:", df.shape)

# Check coverage of trade period
mask = (df.index.get_level_values("datetime") >= "2024-06-25") & (df.index.get_level_values("datetime") <= "2024-07-25")
print("Bars in trade period:", mask.sum())

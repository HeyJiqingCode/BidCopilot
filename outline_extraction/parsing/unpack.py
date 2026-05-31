"""文件解压与遍历——把目录/压缩包/单文件统一成扁平文件清单"""
import zipfile
import tempfile
from pathlib import Path

# 忽略的噪音文件名
_IGNORE_NAMES = {".DS_Store", "Thumbs.db"}
# 被视为压缩包的后缀（.ebid 实测为 ZIP）
_ARCHIVE_SUFFIXES = {".zip", ".ebid"}


def collect_files(input_path: Path) -> list[tuple[str, str]]:
    """递归收集所有可处理文件

    参数:
        input_path: 目录、压缩包或单个文件路径
    返回:
        [(绝对路径字符串, 小写后缀)] 列表；压缩包会被解压到临时目录后收集其内容
    """
    input_path = Path(input_path)
    results: list[tuple[str, str]] = []

    if input_path.is_file():
        _collect_one(input_path, results)
        return results

    for entry in sorted(input_path.rglob("*")):
        if entry.is_file():
            _collect_one(entry, results)
    return results


def _collect_one(file_path: Path, results: list[tuple[str, str]]) -> None:
    """处理单个文件：噪音跳过、压缩包解压、其余登记——内部辅助

    参数:
        file_path: 文件路径
        results: 累积结果列表（原地追加）
    返回: 无（结果写入 results）
    """
    if file_path.name in _IGNORE_NAMES:
        return
    suffix = file_path.suffix.lower()
    if suffix in _ARCHIVE_SUFFIXES and zipfile.is_zipfile(file_path):
        extract_dir = Path(tempfile.mkdtemp(prefix="unpack_"))
        with zipfile.ZipFile(file_path) as z:
            z.extractall(extract_dir)
        for entry in sorted(extract_dir.rglob("*")):
            if entry.is_file() and entry.name not in _IGNORE_NAMES:
                results.append((str(entry), entry.suffix.lower()))
        return
    results.append((str(file_path), suffix))

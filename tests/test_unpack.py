"""文件解压/遍历测试"""
import zipfile
from pathlib import Path
from outline_extraction.parsing.unpack import collect_files


def test_collect_from_directory(tmp_path):
    """目录递归遍历，返回 (路径, 后缀小写)"""
    (tmp_path / "a.docx").write_text("x")
    sub = tmp_path / "sub"
    sub.mkdir()
    (sub / "b.pdf").write_text("y")
    files = collect_files(tmp_path)
    suffixes = sorted(suf for _, suf in files)
    assert suffixes == [".docx", ".pdf"]


def test_collect_single_file(tmp_path):
    """传入单个文件直接返回该文件"""
    f = tmp_path / "only.docx"
    f.write_text("x")
    files = collect_files(f)
    assert len(files) == 1
    assert files[0][1] == ".docx"


def test_unzip_ebid(tmp_path):
    """.ebid（ZIP）应被解压，内部文件被收集"""
    ebid = tmp_path / "tender.ebid"
    with zipfile.ZipFile(ebid, "w") as z:
        z.writestr("TenderData.xml", "<root/>")
    files = collect_files(tmp_path)
    names = sorted(Path(p).name for p, _ in files)
    assert "TenderData.xml" in names


def test_skip_ds_store(tmp_path):
    """.DS_Store 等噪音文件被跳过"""
    (tmp_path / ".DS_Store").write_text("junk")
    (tmp_path / "real.docx").write_text("x")
    files = collect_files(tmp_path)
    names = [Path(p).name for p, _ in files]
    assert ".DS_Store" not in names
    assert "real.docx" in names

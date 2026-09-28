from pathlib import Path
import tempfile
from scientist.chat.scientist_chat import ScientistChatStore, MAX_REQUEST_HISTORY_CHARS, MAX_REQUEST_HISTORY_MESSAGES

with tempfile.TemporaryDirectory() as td:
    store=ScientistChatStore(Path(td))
    fid="F_TEST"
    store.save(fid,[{"role":"user","content":"hello"},{"role":"assistant","content":"world"}])
    assert len(store.load(fid))==2
    p=store.clear(fid)
    assert p.exists(), "clear must leave canonical empty store"
    assert store.load(fid)==[], "clear must atomically empty history"
assert MAX_REQUEST_HISTORY_MESSAGES <= 16
assert MAX_REQUEST_HISTORY_CHARS <= 28000
print("SCIENTIST_CHAT_RESET_SELFTEST PASS")

import os, re
TOOLS = r"C:\Users\Minhsnguhoa\pmca-re\tools"
data = open(os.path.join(TOOLS, "crypter.elf"), "rb").read()
strs = [s.decode("latin1","replace") for s in re.findall(rb"[ -~]{3,}", data)]
print("=== path / updater / env related strings ===")
for s in sorted(set(strs)):
    if re.search(r"updater|UPDATER|tmp_updater|/tmp|env|ENV|getenv|home|HOME|dir|DIR|path|PATH|work|WORK|bodyimg|Firm|0100", s, re.I):
        print("  " + s)

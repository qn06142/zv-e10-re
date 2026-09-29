import os, re, collections

import pathlib
ROOT_REPO = pathlib.Path(__file__).resolve().parents[2]
FW = (ROOT_REPO / 'fw').as_posix()
av = open(os.path.join(FW, "av-cam.bin"), "rb").read()
strs = [s.decode("latin1","replace") for s in re.findall(rb'[ -~]{4,}', av)]
blob = " ".join(strs)

print("=== NETWORK / REMOTE SURFACE (potential RCE attack surface) ===")
for pat in [r'\b(?:ftp|FTP|http|HTTP|TCP|tcp|IP|ip|port|PORT|socket|SOCKET|connect|CONNECT|server|SERVER|client|CLIENT|192\.168|10\.|172\.)[A-Za-z0-9_./: -]{0,30}']:
    seen = sorted(set(re.findall(pat, blob)))[:12]
    for s in seen: print("   ", s[:60])

print("\n=== COMMAND / IPC / MESSAGE HANDLERS (uipc, liro msg) ===")
for pat in [r'\b(?:CMD|cmd|Command|Msg|MSG|Message|Handler|handler|Request|request|Notify|notify|Event|event|Service|service|UIPC|uipc|LIRO|liro)[A-Za-z0-9_]{0,30}']:
    seen = sorted(set(re.findall(pat, blob)))[:18]
    for s in seen: print("   ", s[:60])

print("\n=== CRYPTO / AUTH / SECURE (the decrypt path + any holes) ===")
for pat in [r'\b(?:AES|aes|RSA|rsa|SHA|sha|MD5|md5|key|Key|KEY|cert|Cert|CERT|sign|Sign|SIGN|verify|Verify|secure|Secure|SEC|crypt|Crypt|hash|Hash|nonce|Nonce|password|Password|token|Token|OTP|otp|eFuse|efuse)[A-Za-z0-9_ ()]{0,30}']:
    seen = sorted(set(re.findall(pat, blob)))[:22]
    for s in seen: print("   ", s[:60])

print("\n=== PARSER / FILE / FORMAT (classic memory-corruption surface) ===")
for pat in [r'\b(?:parse|Parse|PARSE|decode|Decode|DECODE|encode|Encode|read|Read|Write|load|Load|XML|xml|JSON|json|EXIF|exif|TIFF|tiff|JPEG|jpeg|thumbnail|Thumbnail|format|Format|header|Header)[A-Za-z0-9_]{0,28}']:
    seen = sorted(set(re.findall(pat, blob)))[:22]
    for s in seen: print("   ", s[:60])

# function symbols that look like exposed entry points / init / handler
print("\n=== suspicious-looking entry/handler function symbols ===")
syms = sorted(set(re.findall(r'\b([A-Za-z_][A-Za-z0-9_]{3,})\s*\(', blob)))
interesting = [s for s in syms if re.search(r'(Handler|handler|Callback|callback|Entry|entry|Main|main|Init|init|Proc|proc|Task|task|Thread|thread|Server|server|Recv|recv|Receive|Send|Exec|exec|Process|process|Parse|parse|Decode|decode)', s)]
for s in interesting[:60]:
    print("   ", s)
print("   ... total interesting handler symbols:", len(interesting))

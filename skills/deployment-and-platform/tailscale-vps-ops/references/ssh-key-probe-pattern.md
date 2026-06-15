# SSH Key Probe Pattern

Use this when the VPS is reachable but you do not know which SSH key or user is correct.

## Inputs To Set First

```bash
TARGET_HOST="<vps-host-or-tailscale-ip>"
TARGET_USERS="ubuntu root"
```

If the user already gave a preferred remote user, try that one first.

## Quick Probe Script

```bash
for user in $TARGET_USERS; do
  for key in ~/.ssh/*.pem ~/.ssh/id_*; do
    [ -f "$key" ] || continue
    [ "${key##*.}" = "pub" ] && continue
    ssh -i "$key" \
      -o StrictHostKeyChecking=no \
      -o UserKnownHostsFile=/dev/null \
      -o ConnectTimeout=5 \
      -o BatchMode=yes \
      "$user@$TARGET_HOST" "echo ok" 2>/dev/null && \
      echo "WORKS: user=$user key=$key" && break 2
  done
done
```

## Why This Pattern Works

- `.pem` files are common for cloud-provider VPS keys
- `id_*` covers standard local SSH key names
- `BatchMode=yes` prevents a password prompt from hanging the session
- `ConnectTimeout=5` keeps the probe fast

## Follow-Up Rule

Once a working combination is found:

1. reuse it for the rest of the session
2. stop probing more keys
3. surface the chosen user and key path in your response

## Common Lessons

- A valid GitHub or workstation SSH key is not automatically a valid VPS key
- If the host key was rotated, clear the known-hosts entry before retrying
- If Tailscale node status is inactive, fix network reachability before blaming the key

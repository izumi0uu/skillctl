# SSH Remote Python Script Execution: Heredoc Traps

Use this when you need to write or execute a multi-line Python snippet on a remote VPS over SSH.

## Problem

A remote heredoc such as:

```bash
ssh <user>@<host> "cat > /tmp/script.py <<'EOF'
...
EOF
python3 /tmp/script.py"
```

can fail because the remote shell misparses the heredoc delimiter or content.

## Symptom

Typical errors look like:

```text
parse error near `end'
```

or a partially written script that fails later.

## Preferred Solutions

### 1. Use `echo` line by line

Most reliable for short scripts:

```bash
ssh <user>@<host> "
  echo 'import re' > /tmp/patch.py
  echo 'print(\"hello\")' >> /tmp/patch.py
  python3 /tmp/patch.py
"
```

### 2. Use `python3 -c`

Good for short read or patch operations:

```bash
ssh <user>@<host> "python3 -c \"print('hello')\""
```

### 3. Pipe to `python3 -`

Let the local shell own the heredoc instead of the remote shell:

```bash
ssh <user>@<host> 'python3 -' <<'PYEOF'
print("hello")
PYEOF
```

### 4. Use base64 for complex scripts

```bash
SCRIPT=$(printf '%s' 'print("hello")' | base64)
ssh <user>@<host> "echo $SCRIPT | base64 -d | python3"
```

## Best Practice

For remote VPS work:

1. prefer `echo` for short scripts
2. prefer `python3 -c` for simple checks
3. use stdin or base64 when quoting becomes fragile
4. inspect the written file before execution if the patch matters

## Validate Before Running

```bash
ssh <user>@<host> "python3 -m py_compile /tmp/patch.py && python3 /tmp/patch.py"
```

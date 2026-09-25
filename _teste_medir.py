import tbh_baus as b

print("MEDIR_EVAL tem", len(b.MEDIR_EVAL), "chars")
r = b._ab("eval", b.MEDIR_EVAL, timeout=60)
print("resposta:", r[:300])

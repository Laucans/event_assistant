"""Le raffinage d'une issue : son corps, ecrit section par section, par rounds.

`workflow` porte le `Blueprint`, `settings` ce qui varie d'un round a
l'autre, `preconditions` la porte du workflow. Les sections, les rounds et la
publication sont dans `internals/` ; les prompts dans `stages/`.
"""

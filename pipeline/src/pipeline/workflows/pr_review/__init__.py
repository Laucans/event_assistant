"""La revue consultative d'une PR, en deux passes.

`workflow` porte `PrReview`, `settings` ce qui varie d'une revue a l'autre,
`preconditions` et `postconditions` les deux gardes du contrat. Les passes,
les regles de saut et la publication sont dans `internals/`.
"""

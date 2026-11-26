#!/usr/bin/env bash
# Shared helpers for the acceptance gates.
#
# `warn_untracked` exists because of roadmap H18: every git-scoped check reads
# the **index**, so a file that is not `git add`-ed is outside the measurement
# and a gate run before staging is not the gate CI runs. That bit three times
# in one session — the single-copy gate missed a duplicate in its own test file
# until the file was committed, C3's data-dependent test was green locally and
# red in CI, and H10's randomness probe matched its own pattern string only
# once it was tracked.
#
# It warns rather than fails on purpose. A hard refusal would make every gate
# unusable mid-edit, and a gate that cannot be run during development stops
# being run at all. The exception is `H17.sh`, which refuses outright: it
# measures a clone, so it is structurally incapable of seeing unstaged work and
# a warning there would be an invitation to misread the result.

warn_untracked() {
    local untracked
    untracked="$(git ls-files --others --exclude-standard -- "$@" 2>/dev/null | head -20)"
    if [ -n "$untracked" ]; then
        echo "⚠️  UYARI — bu ölçüm git indeksini okur; aşağıdaki dosyalar İZLENMİYOR,"
        echo "    yani kapsamın dışında kaldılar (H18). Ölçümü anlamlı kılmak için"
        echo "    'git add' et ve kapıyı tekrar koş:"
        echo "$untracked" | sed 's/^/      /'
        return 1
    fi
    return 0
}

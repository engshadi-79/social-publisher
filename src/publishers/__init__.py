from .facebook import Facebook
from .instagram import Instagram
from .telegram import Telegram
from .threads import Threads
from .x import X

PUBLISHERS = {p.name: p() for p in (Facebook, Instagram, Threads, Telegram, X)}

from .facebook import Facebook
from .instagram import Instagram
from .linkedin import LinkedIn
from .telegram import Telegram
from .threads import Threads

PUBLISHERS = {p.name: p() for p in (Facebook, Instagram, Threads, LinkedIn, Telegram)}

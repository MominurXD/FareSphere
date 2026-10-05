# Live provider adapter placeholder.
#
# Skyscanner API access requires an approved partnership/API key.
# The frontend must never receive the provider key.


class SkyscannerProvider:
    name = "skyscanner"

    async def search(self, *args, **kwargs):
        raise NotImplementedError("Configure an approved Skyscanner API key before enabling live search.")

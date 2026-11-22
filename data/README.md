# English word list

`english_words.txt.gz` contains the 30,000 most frequent English words from
[wordninja](https://github.com/keredson/wordninja), one word per line in
descending frequency order.

It is used only to re-join English words that the Chinese Paraformer model
emits as space-separated letters, for example:

```text
l o v e  ->  love
i a m    ->  i am
```

The list is bundled with the project so the shim does not depend on a system
dictionary and works offline on macOS, Linux, and Windows.

## Regenerate

```bash
python -m pip download --no-deps wordninja -d /tmp/wordninja
python - <<'PY'
import gzip, io, pathlib, tarfile

src = next(pathlib.Path("/tmp/wordninja").glob("wordninja-*.tar.gz"))
with tarfile.open(src) as t:
    raw = gzip.decompress(
        t.extractfile("wordninja-2.0.0/wordninja/wordninja_words.txt.gz").read()
    ).decode("utf-8")

words = raw.split()[:30000]
buf = io.BytesIO()
with gzip.GzipFile(fileobj=buf, mode="wb", mtime=0) as gz:
    gz.write(("\n".join(words) + "\n").encode("utf-8"))
pathlib.Path("data/english_words.txt.gz").write_bytes(buf.getvalue())
PY
```

## License

The word list is derived from wordninja, which is distributed under the MIT
License:

```text
MIT License

Copyright (c) 2017 Derek Anderson

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
```

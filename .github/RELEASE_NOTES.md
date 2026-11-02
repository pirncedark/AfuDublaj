**Afu Dublaj — real-time screen translation and natural dubbing for games and videos, now in the Afu family.**

## Download

**Windows 10/11 (64-bit):** download `AfuDublaj-…-windows-x64.zip` below, extract it anywhere and run `AfuDublaj.exe`. The `.sha256` file is the checksum used by the built-in updater.
On first launch the app downloads the translation model you choose (~650 MB – 1.4 GB) straight from Hugging Face — after that it works fully offline.

> Windows SmartScreen may warn about an unsigned app: click **More info → Run anyway**.
> If the translator fails to load, install the [Microsoft Visual C++ Redistributable](https://aka.ms/vs/17/release/vc_redist.x64.exe).

## Türkçe ayrıntılar

- **Afu görünümü:** koyu Afu renkleri ve yeni ikon; arayüz Türkçe, Almanca ve Rusça tam yerelleştirildi.
- **Otomatik güncelleme:** yeni sürüm arka planda denetlenir, sha256 ile doğrulanır; kurulumdan sonra yeni sürüm açılmazsa eskisine otomatik geri dönülür.
- **Doğal ses:** internet varken Microsoft'un nöral Türkçe sesleri (Emel/Ahmet) kullanılır; internet yoksa ya da ilk ses 2 saniyede gelmezse çevrimdışı Piper sesi devreye girer.
- **Ayarlar:** Güncelleme ve Paylaş kartları eklendi. Eski ayar klasörü (`Lingolay`) ilk açılışta otomatik `AfuDublaj` klasörüne aktarılır.

## Credits / Atıf

Afu Dublaj is based on [Lingolay](https://github.com/keremss7/lingolay) by keremss7 and contributors, released under the GNU GPL-3.0; this build keeps the license and adds the changes above.

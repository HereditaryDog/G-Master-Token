# Cloudflare Tunnel

推荐将这台本地电脑通过 Cloudflare Tunnel 暴露给同事访问。

需要准备：

1. Cloudflare 账号
2. 一个托管在 Cloudflare 的域名
3. 一个 Tunnel Token

拿到 token 后，将其写入 `.env.server`：

```env
CLOUDFLARE_TUNNEL_TOKEN=your-token
```

然后使用带 `public` profile 的 Compose 启动：

```powershell
docker compose --env-file .env.server --profile public up -d --build
```

建议将测试域名指向 tunnel，例如：

- `test.example.com`

这样你的同事就可以通过固定域名访问本机上的站点。

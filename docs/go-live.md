# Đưa PaySeal vào vận hành với payOS

## Trạng thái hiện tại

Đã tích hợp SDK chính thức payOS 1.1.0 cho kênh thu và kênh chi riêng, khóa mã hóa theo tổ chức, kiểm tra tài khoản, MFA, lưu lệnh trước khi gửi, idempotency và đối soát định kỳ.

**Chưa có tài khoản ngân hàng/payOS, khóa thật, tên miền hoặc máy chủ được cấu hình. Chưa nghiệm thu với nhà cung cấp thật; không có giao dịch tiền thật nào được thực hiện.** Bản local vẫn sandbox. Kiểm thử dùng database riêng và nhà cung cấp giả lập.

Thu tiền là khoản phải thu vào kênh của tổ chức, độc lập với yêu cầu chi tiền đã ký. API nhận lệnh hoặc tham số `paid/success` trên trình duyệt không chứng minh tiền đã đến. QR xác minh chữ ký PaySeal khác QR chuyển khoản trên trang payOS.

## Bạn cần chuẩn bị gì?

1. Chuẩn bị pháp nhân/thông tin kinh doanh và tài khoản nhận tiền phù hợp. Xác nhận với payOS tài khoản/kênh chi dự kiến được hỗ trợ và kích hoạt; không chọn ngân hàng chỉ vì logo hoặc phí.
2. Đăng ký trên [trang quản lý payOS](https://my.payos.vn), hoàn thành xác minh nhà cung cấp, tạo kênh thu và xin kích hoạt **kênh chi riêng**. Khóa kênh thu không mặc nhiên có quyền chi; nguồn chi phụ thuộc đối tác ngân hàng/ví và dịch vụ đã được chấp thuận.
3. Hoàn thiện hồ sơ PaySeal và xét duyệt độc lập theo README. Xét duyệt trong PaySeal không thay cho xác minh pháp nhân/chủ tài khoản của ngân hàng/payOS.
4. Có tên miền và máy chủ do bạn kiểm soát, Docker Compose, DNS A/AAAA đúng máy chủ, TCP 80/443 công khai. Localhost không nhận được webhook thật. Repo không tự mua dịch vụ hoặc mở tài khoản.
5. Hoàn tất kiểm tra bảo mật/vận hành độc lập: quản lý khóa ký, kho bằng chứng được hỗ trợ, sao lưu/khôi phục, giám sát, trách nhiệm xử lý sự cố và các yêu cầu hợp đồng/tuân thủ áp dụng.

Đối chiếu yêu cầu hiện hành tại [API payOS](https://payos.vn/docs/api/), [Python SDK](https://payos.vn/docs/sdks/back-end/python/) và [kênh chi payOS](https://payos.vn/ra-mat-kenh-chi-tren-payos-giai-phap-chi-tu-dong-qua-api/). Không gửi khóa API trong chat.

## Cài production mới

Đây là bộ cấu hình triển khai một máy chủ, **không phải chứng nhận đủ an toàn để chi tiền thật**. Không dùng `.env` phát triển. Mã nguồn chặn seed tài khoản demo khi `ENVIRONMENT=production`.

Sau khi có tên miền thật, chạy trong thư mục dự án trên máy của bạn:

```powershell
.\scripts\prepare-production.ps1 -Domain "ten-mien-cua-ban.vn"
```

Script sinh `.env.production` với các khóa ngẫu nhiên riêng, hạn chế quyền đọc tệp, không in khóa và không ghi đè tệp cũ. Mặc định `PAYMENTS_LIVE_ENABLED=false`, `TRANSFER_MODE=disabled`. Có thể chuyển tệp sang máy chủ qua kênh bảo mật, đặt quyền `600` trên Linux; không gửi/commit tệp.

```text
docker compose --env-file .env.production -f docker-compose.production.yml config -q
docker compose --env-file .env.production -f docker-compose.production.yml up -d --build
```

Production dùng project/volume riêng, không ghi vào dữ liệu Docker local. PostgreSQL, MinIO và backend không mở cổng trực tiếp ra máy chủ. Caddy nhận 80/443 và quản lý HTTPS, cần đáp ứng [điều kiện DNS/cổng/volume chứng chỉ](https://caddyserver.com/docs/automatic-https).

**Không khôi phục database cũ dưới khóa mã hóa mới sinh.** Tài khoản/MFA/khóa API/khóa ký đang lưu sẽ không giải mã được. Chuyển dữ liệu cũ cần kế hoạch giữ/luân chuyển khóa và sao lưu database, object storage, signing volume cùng kiểm tra khôi phục. Không tự thay khóa của bản local đang chạy.

## Kết nối và kích hoạt

1. Đăng ký người dùng thật, tạo tổ chức, bật MFA và xét duyệt hồ sơ độc lập. Không dùng tài khoản/mật khẩu demo cho production.
2. Sau kiểm tra production, quản trị đặt `PAYMENTS_LIVE_ENABLED=true`. Có thể giữ `TRANSFER_MODE=disabled` trong lúc kết nối/nghiệm thu kênh thu.
3. Cập nhật dịch vụ đọc cấu hình:

```text
docker compose --env-file .env.production -f docker-compose.production.yml up -d --force-recreate backend reconciliation
```

4. Mở **Kết nối thanh toán**. Màn hình nêu điều kiện còn thiếu. Khi đủ điều kiện, chủ tổ chức bấm **Tôi đã có khóa API**, nhập bộ khóa riêng của kênh, BIN, số/tên tài khoản đúng như payOS trả về, xác nhận quyền quản lý và nhập MFA. Kết nối không chuyển thử tiền.
5. Kênh thu đăng ký callback `/api/v1/payment-integrations/webhooks/payos/{channel_id}`. Chữ ký được kiểm tra; mẫu đăng ký không tạo khoản thu. Chỉ kích hoạt kênh khi tài khoản khớp.
6. Dùng **Thu tiền** tạo khoản thu, mở/sao chép liên kết payOS và gửi khách. Webhook được xác thực rồi máy chủ truy vấn số tiền tích lũy, không cộng tiền trực tiếp từ callback.
7. Sau nghiệm thu và kích hoạt dịch vụ chi, quản trị mới đặt `TRANSFER_MODE=live`. Tạo người thụ hưởng với BIN 6 số đã xác nhận, ký yêu cầu mới sau xét duyệt doanh nghiệp. Người phê duyệt độc lập kiểm tra và xác nhận chi thật bằng MFA. Hạn mức khởi đầu **1.000.000 VND/lệnh** là cấu hình an toàn của ứng dụng, không phải hạn mức payOS công bố.

Không thực hiện giao dịch thử thật khi chưa có chấp thuận cụ thể của người có quyền.

## Khôi phục khi chưa rõ kết quả

- `QUEUED`: đã lưu, chưa bắt đầu gửi. Người phê duyệt xác nhận lại bằng MFA; máy chủ kiểm tra lại chữ ký/phiên bản/hiệu lực/hồ sơ/kênh/hạn mức.
- `DISPATCHING` hoặc `UNKNOWN`: có thể nhà cung cấp đã nhận lệnh. Chỉ đối soát tham chiếu đã lưu; không tự gửi lại hay đổi idempotency key để tạo lệnh thay thế. Không tìm thấy kết quả vẫn cần kiểm tra với nhà cung cấp/đơn vị vận hành.
- `SUBMITTED`/`ON_HOLD`: chờ kết quả nhà cung cấp, chưa đồng nghĩa tiền đã đến người nhận.
- `REVERSED`: nhà cung cấp báo hoàn trả, không phải thất bại chưa chi. Worker theo dõi lệnh thành công trong 30 ngày để phát hiện trạng thái này.
- Khoản thu `UNKNOWN` được tra cứu bằng order code. API tra cứu không trả toàn bộ thông tin tài khoản/checkout: nếu chưa có URL đã kiểm tra, hệ thống không tự suy diễn URL hoặc tạo lại liên kết. Kiểm tra trong dashboard payOS trước khi chia sẻ.
- Ngắt kênh chặn giao dịch mới, không tự hủy/hoàn tiền lệnh đã gửi hoặc xóa lịch sử. Khóa cũ giữ mã hóa để đối soát; cần chính sách lưu trữ/thu hồi khóa riêng.

Worker chỉ truy vấn, **không gửi lệnh chi**. Mỗi lượt tối đa 100 lệnh chi + 100 khoản thu; mỗi bản ghi cách lần kiểm tra trước tối thiểu 60 giây. Theo dõi log `unresolved`, cấu hình cảnh báo; `healthz` không chứng minh đối soát thành công.

```text
docker compose --env-file .env.production -f docker-compose.production.yml exec reconciliation python -m app.reconcile_worker --once
```

## Phần chưa được nghiệm thu bên ngoài

Chưa thử tài khoản payOS thật; chưa xác minh đăng ký doanh nghiệp tự động, hạch toán kép/đối soát sao kê và settlement độc lập, phí/hoàn tiền/chargeback, hạn mức ngày, HSM/KMS, WORM/SIEM, chống mã độc PDF hoặc vận hành HA. Kiểm tra tài khoản trả về của nhà cung cấp không chứng nhận quyền sở hữu pháp lý. Virtual-account, lỗi đặc thù và quy tắc ngân hàng cần nghiệm thu với kênh đã cấp.

Không bật tiền thật trước khi hoàn tất các kiểm tra, trách nhiệm, hợp đồng, giới hạn và khôi phục cần thiết.

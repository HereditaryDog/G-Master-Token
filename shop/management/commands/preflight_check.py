import json

from django.core.management.base import BaseCommand

from shop.deployment_checks import run_readiness_checks


class Command(BaseCommand):
    help = "运行上线前预检，检查数据库、迁移、邮件、支付、供货等关键配置。"

    def add_arguments(self, parser):
        parser.add_argument("--json", action="store_true", dest="as_json", help="以 JSON 格式输出结果。")

    def handle(self, *args, **options):
        result = run_readiness_checks()
        if options["as_json"]:
            self.stdout.write(json.dumps(result, ensure_ascii=False, indent=2))
        else:
            self.stdout.write("上线预检结果")
            self.stdout.write(f"ok={result['ok']}")
            self.stdout.write(f"internal_test_ready={result['internal_test_ready']}")
            self.stdout.write(f"external_user_test_ready={result['external_user_test_ready']}")
            for check in result["checks"]:
                self.stdout.write(f"[{check['status'].upper()}] {check['label']}: {check['detail']}")

        if not result["ok"]:
            raise SystemExit(1)

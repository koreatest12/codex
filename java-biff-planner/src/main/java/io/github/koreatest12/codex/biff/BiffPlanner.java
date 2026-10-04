package io.github.koreatest12.codex.biff;

import java.util.List;
import java.util.Locale;

public final class BiffPlanner {
    private record Item(String time, String title, String detail) {}

    private static final List<Item> DAY1 = List.of(
        new Item("08:02 / 08:05", "죽전/오리 → 수서", "접근시간이 비슷하면 오리역이 1정거장·약 3분 유리. 수서 08:31 전후 도착 목표."),
        new Item("09:20-12:01", "SRT 수서 → 부산", "예매 승차권 기준."),
        new Item("13:10 전후", "신라스테이 해운대", "체크인 전이면 짐 보관. 공식 일반 체크인 15:00."),
        new Item("15:45", "영화의전당 이동", "해운대역 2호선 → 센텀시티역 → 도보."),
        new Item("17:00-18:00", "개막식 입장", "지정좌석 6구역 11열 11번."),
        new Item("18:00-19:00", "레드카펫", "영화의전당 루프씨어터."),
        new Item("19:00-20:00", "개막식 공식행사", ""),
        new Item("20:20-21:40", "개막작", "〈낮과 밤은 서로에게〉."),
        new Item("22:20 전후", "해운대 복귀", "다음 날 이른 일정 대비.")
    );

    private static final List<Item> DAY2 = List.of(
        new Item("06:30", "기상", "호텔 조식 미포함."),
        new Item("06:50-07:25", "해운대 외부 아침", "돼지국밥/복국처럼 따뜻하고 빠른 식사."),
        new Item("08:00-08:10", "체크아웃", "캐리어 소지."),
        new Item("08:40-08:55", "센텀시티역 짐 보관", "빈자리 보장 없음."),
        new Item("09:40-12:02", "〈꿀알바〉", "롯데시네마 센텀시티 4관, 142분."),
        new Item("12:02 이후", "〈꿀알바〉 GV", "종료 시각은 현장 진행에 따라 변동."),
        new Item("GV 종료-13:20", "빠른 점심", "센텀 내부. 13:20까지 4관 복귀."),
        new Item("13:40-15:30", "〈자필〉", "롯데시네마 센텀시티 4관, 110분."),
        new Item("15:30 이후", "〈자필〉 GV 미관람", "기본 계획. 당일 공식 게스트에 따라 재판단 가능."),
        new Item("15:40-16:55", "센텀 → 부산역", "짐 회수 후 2호선 → 서면 → 1호선."),
        new Item("18:51-21:29", "SRT 부산 → 수서", "예매 승차권 기준.")
    );

    private static final List<String> FOOD = List.of(
        "해운대 아침 1순위: 해운대오복돼지국밥",
        "해운대 따뜻한 국물: 금수복국 해운대본점",
        "해운대 유명식: 해운대 암소갈비집(대기시간 주의)",
        "센텀 영화 사이: 딤딤섬 / 사리원 한우양지탕 / 시간이 없으면 푸드홀",
        "센텀 커피: 폴 바셋 센텀시티 몰점",
        "해운대 커피: 블랙업커피 / 까사 부사노"
    );

    private BiffPlanner() {}

    public static void main(String[] args) {
        String command = args.length == 0 ? "all" : args[0].toLowerCase(Locale.ROOT);
        switch (command) {
            case "all" -> {
                printHeader();
                printDay("10월 6일", DAY1);
                printDay("10월 7일", DAY2);
                printFood();
                printHotel();
                printChecklist();
            }
            case "summary" -> {
                printHeader();
                printDay("10월 6일", DAY1);
                printDay("10월 7일", DAY2);
            }
            case "day1" -> printDay("10월 6일", DAY1);
            case "day2" -> printDay("10월 7일", DAY2);
            case "food" -> printFood();
            case "hotel" -> printHotel();
            case "toolchain" -> printToolchain();
            case "help", "--help", "-h" -> printHelp();
            default -> {
                System.err.println("Unknown command: " + command);
                printHelp();
                System.exit(2);
            }
        }
    }

    private static void printHeader() {
        System.out.println("BIFF 2026 부산 1박2일 일정");
        System.out.println("숙소: 신라스테이 해운대 | 〈자필〉 본편 포함 / GV 기본 미관람");
        System.out.println();
    }

    private static void printDay(String day, List<Item> items) {
        System.out.println("== " + day + " ==");
        for (Item item : items) {
            System.out.printf("%-15s %-24s %s%n", item.time(), item.title(), item.detail());
        }
        System.out.println();
    }

    private static void printFood() {
        System.out.println("== 음식/커피 ==");
        FOOD.forEach(item -> System.out.println("- " + item));
        System.out.println();
    }

    private static void printHotel() {
        System.out.println("== 신라스테이 해운대 ==");
        System.out.println("- 주소: 부산 해운대구 해운대로570번길 46");
        System.out.println("- 공식 일반 체크인 15:00 / 체크아웃 12:00");
        System.out.println("- 7~8월은 공식 체크아웃 11:00 안내가 있으나 10월은 일반 기준");
        System.out.println("- 예약 바우처 표기가 다르면 호텔에 최종 확인");
        System.out.println("- 이번 일정은 08:00~08:10 조기 체크아웃 예정");
        System.out.println();
    }

    private static void printChecklist() {
        System.out.println("== 준비물 ==");
        System.out.println("- BIFF 모바일티켓 / SRT 승차권 / 신분증 / 교통카드");
        System.out.println("- 휴대전화 / 보조배터리 / 충전 케이블");
        System.out.println("- 얇은 재킷 또는 블레이저 / 편한 신발 / 작은 접이식 우산");
        System.out.println("- 개인 세면용품 / 간단 간식");
        System.out.println("- 출발 전 날씨·GV 게스트·지하철·식당 영업시간 재확인");
    }

    private static void printToolchain() {
        System.out.println("java.version=" + System.getProperty("java.version"));
        System.out.println("java.vendor=" + System.getProperty("java.vendor"));
        System.out.println("java.home=" + System.getProperty("java.home"));
        System.out.println("os.name=" + System.getProperty("os.name"));
        System.out.println("os.arch=" + System.getProperty("os.arch"));
    }

    private static void printHelp() {
        System.out.println("Usage: java -jar biff-planner.jar [all|summary|day1|day2|food|hotel|toolchain]");
    }
}

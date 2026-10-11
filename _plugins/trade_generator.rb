require 'json'

module Jekyll
  # 금액·날짜·평형 표기 도우미
  module TradeFmt
    module_function

    # 만원 단위 정수 -> "12억 3,500만원"
    def man(n)
      n = n.to_i
      return '-' if n <= 0
      eok = n / 10_000
      rest = n % 10_000
      if eok.positive?
        rest.zero? ? "#{eok}억원" : "#{eok}억 #{rest.to_s.reverse.scan(/\d{1,3}/).join(',').reverse}만원"
      else
        "#{n.to_s.reverse.scan(/\d{1,3}/).join(',').reverse}만원"
      end
    end

    def ymd(n)
      n = n.to_i
      return '-' if n <= 0
      format('%04d.%02d.%02d', n / 10_000, (n / 100) % 100, n % 100)
    end

    def ym(n)
      n = n.to_i
      format('%04d년 %d월', n / 10_000, (n / 100) % 100)
    end

    def area_label(a, py)
      "전용 #{a}㎡(약 #{py}평형)"
    end

    def josa_i(w)
      c = w.to_s.strip[-1]
      return '이' if c.nil?
      o = c.ord
      (o >= 0xAC00 && o <= 0xD7A3 && (o - 0xAC00) % 28 != 0) ? '이' : '가'
    end

    def josa_eun(w)
      c = w.to_s.strip[-1]
      return '은' if c.nil?
      o = c.ord
      (o >= 0xAC00 && o <= 0xD7A3 && (o - 0xAC00) % 28 == 0) ? '는' : '은'
    end

    def pad(n, k)
      n.to_s.rjust(k, '0')
    end
  end

  # ── 거래 데이터 로드 + 기존 K-apt 단지 페이지에 병합 ─────────────
  class TradeDataGenerator < Generator
    safe true
    priority :high

    def generate(site)
      dir = File.join(site.source, '_rawdata')
      files = Dir.glob(File.join(dir, 'trades_*.json'))
      all = []
      files.sort.each { |f| all.concat(JSON.parse(File.read(f, encoding: 'utf-8'))) }
      meta_path = File.join(dir, 'trade_meta.json')
      meta = File.exist?(meta_path) ? JSON.parse(File.read(meta_path)) : {}
      site.data['trade_meta'] = meta
      return if all.empty?

      by_code = {}
      all.each { |t| by_code[t['code']] = t unless t['code'].to_s.empty? }
      matched = 0
      (site.data['apt_all'] || []).each do |a|
        t = by_code[a['code']]
        next unless t
        a['trade'] = TradeText.build(t.merge('name' => a['aptName']), meta)
        a['tradeDong'] = t['dong']
        matched += 1
      end
      only = all.select { |t| t['code'].to_s.empty? }
      site.data['trade_only'] = only
      site.data['trade_all'] = all
      Jekyll.logger.info 'TradeGenerator:', "거래 데이터 #{all.size}단지 (K-apt 병합 #{matched}, 전용 #{only.size})"
    end
  end

  # 단지 1건의 거래 요약(표시용 문자열)을 만든다
  module TradeText
    module_function

    F = TradeFmt

    def build(t, meta)
      tg = t['tg'] || []
      rg = t['rg'] || []
      name = t['name']
      top = tg.first
      groups = tg.map do |g|
        { 'label' => F.area_label(g['a'], g['py']), 'n12' => g['n12'], 'avg' => F.man(g['avg12']), 'min' => F.man(g['min12']),
          'max' => "#{F.man(g['max3'])} (#{F.ymd(g['max3d'])}, #{g['max3f']}층)", 'last' => "#{F.man(g['last'][2])} (#{F.ymd(g['last'][0])}, #{g['last'][1]}층)" }
      end
      rents = rg.map do |g|
        { 'label' => "전용 #{g['a']}㎡(약 #{(g['a'] * 1.32 / 3.3058).round}평형)", 'nj' => g['nj'], 'avgj' => g['avgj'].positive? ? F.man(g['avgj']) : '-',
          'nw' => g['nw'], 'avgw' => g['nw'].positive? ? "#{F.man(g['avgwd'])} / 월 #{g['avgwm']}만원" : '-' }
      end
      recent = (t['t'] || []).map { |r| { 'date' => F.ymd(r[0]), 'area' => r[1], 'floor' => r[2], 'amt' => F.man(r[3]) } }
      recent_r = (t['r'] || []).map { |r| { 'date' => F.ymd(r[0]), 'area' => r[1], 'floor' => r[2], 'dep' => F.man(r[3]), 'mon' => r[4].to_i.positive? ? "#{r[4]}만원" : '전세' } }
      years = (t['yr'] || []).map { |y| { 'year' => y[0], 'n' => y[1], 'avg' => F.man(y[2]) } }

      s = +"#{name}#{F.josa_eun(name)} #{t['doShort']} #{t['sigungu']} #{t['dong']}에 있는 아파트"
      s << "(#{t['by']}년 준공)" if t['by'].to_i.positive?
      s << '입니다. '
      if top
        s << "최근 12개월 동안 매매 #{t['n12']}건이 신고됐고, 가장 많이 거래된 #{F.area_label(top['a'], top['py'])}의 평균 거래가는 #{F.man(top['avg12'])}(최저 #{F.man(top['min12'])})입니다. "
        s << "최근 3년 내 최고가는 #{F.man(top['max3'])}(#{F.ymd(top['max3d'])}, #{top['max3f']}층)이고, 가장 최근 거래는 #{F.ymd(top['last'][0])} #{top['last'][1]}층 #{F.man(top['last'][2])}입니다."
      else
        s << '최근 12개월 동안 신고된 매매 거래는 없습니다.'
      end
      jr = rg.first
      if jr
        parts = []
        parts << "전세 #{jr['nj']}건(평균 #{F.man(jr['avgj'])})" if jr['nj'].positive?
        parts << "월세 #{jr['nw']}건(평균 보증금 #{F.man(jr['avgwd'])}, 월 #{jr['avgwm']}만원)" if jr['nw'].positive?
        s << " 같은 기간 #{F.area_label(jr['a'], (jr['a'] * 1.32 / 3.3058).round)}에서 신고된 전월세는 #{parts.join(', ')}입니다." unless parts.empty?
      end
      ratio = nil
      if top && jr && top['a'] == jr['a'] && jr['avgj'].positive? && top['avg12'].positive?
        ratio = (jr['avgj'] * 100.0 / top['avg12']).round
        s << " 전세가율(평균 전세가÷평균 매매가)은 약 #{ratio}%입니다."
      end
      hi = t['hi'] || []
      s << " 최근 30일 안에 3년 내 최고가를 경신한 거래(신고가)가 #{hi.size}건 있습니다." unless hi.empty?

      faq = []
      if top
        faq << ["#{name} #{top['a']}㎡ 실거래가는 얼마인가요?", "최근 12개월 #{F.area_label(top['a'], top['py'])} 매매 #{top['n12']}건의 평균은 #{F.man(top['avg12'])}, 최저 #{F.man(top['min12'])}, 최근 3년 최고 #{F.man(top['max3'])}입니다. 층·동·거래 시점에 따라 차이가 큽니다."]
      end
      faq << ["#{name} 전세·월세 시세는 어떤가요?", jr ? "최근 12개월 신고 기준 전세 #{jr['nj']}건, 월세 #{jr['nw']}건입니다. 전세 평균은 #{jr['avgj'].positive? ? F.man(jr['avgj']) : '신고 건수 부족'}입니다." : '최근 12개월 신고된 전월세 거래가 없습니다.']
      faq << ['이 실거래가는 어디서 가져온 정보인가요?', '국토교통부 실거래가 공개시스템(공공데이터포털 아파트 매매·전월세 실거래 자료)의 신고 정보입니다. 계약일 기준이며 해제된 거래는 제외했고, 신고 지연으로 최근 며칠 거래는 아직 반영되지 않을 수 있습니다.']
      {
        'summary' => s, 'groups' => groups, 'rents' => rents, 'recent' => recent, 'recentR' => recent_r, 'years' => years, 'faq' => faq.map { |q, a| { 'q' => q, 'a' => a } },
        'n12' => t['n12'], 'n36' => t['n36'], 'nr12' => t['nr12'], 'last' => t['last'], 'ratio' => ratio, 'hi' => hi.size,
        'asOf' => F.ymd(meta['latest'] || 0)
      }
    end

    # 단지 목록 행(허브용)
    def row(t, url)
      tg = t['tg'] || []
      top = tg.first
      {
        'name' => t['name'], 'url' => url, 'by' => t['by'], 'n12' => t['n12'], 'nr12' => t['nr12'],
        'rep' => top ? "#{F.area_label(top['a'], top['py'])} 평균 #{F.man(top['avg12'])}" : '-',
        'last' => t['last'].to_i.positive? ? F.ymd(t['last']) : '-', 'hi' => (t['hi'] || []).size
      }
    end
  end

  class TradeBasePage < Page
    def setup(site, dir, layout)
      @site = site
      @base = site.source
      @dir = dir
      @name = 'index.html'
      process(@name)
      read_yaml(File.join(@base, '_layouts'), "#{layout}.html")
      data['layout'] = layout
    end

    def seo(title, desc)
      data['title'] = title
      data['description'] = desc[0, 155]
    end
  end

  # ── 실거래 전용 단지 페이지(K-apt 에 없는 단지) ────────────────
  class TradeOnlyPage < TradeBasePage
    def initialize(site, t, meta)
      slug = TradeGenerator.slug_of(t)
      setup(site, "trade/#{slug}", 'trade_apt')
      tr = TradeText.build(t, meta)
      name = t['name']
      data['aptName'] = name
      data['doShort'] = t['doShort']
      data['sigungu'] = t['sigungu']
      data['dong'] = t['dong']
      data['jibun'] = t['jibun']
      data['builtYear'] = t['by']
      data['trade'] = tr
      data['faq'] = tr['faq']
      seo("#{name} 실거래가·전세 시세 | #{t['doShort']} #{t['sigungu']} #{t['dong']} #{t['jibun']}", "#{t['doShort']} #{t['sigungu']} #{t['dong']} #{name} 아파트 실거래가 #{tr['n12'].to_i.positive? ? "(최근 12개월 #{tr['n12']}건)" : ''}와 전세·월세 시세, 평형별 최고·최저가를 확인하세요.")
    end
  end

  # ── 동 허브 ──────────────────────────────────────────────
  class TradeDongPage < TradeBasePage
    def initialize(site, do_short, sg, dong, list, rows, neighbors, meta)
      setup(site, "region/#{do_short}/#{sg}/#{dong}", 'trade_dong')
      total12 = list.sum { |t| t['n12'].to_i }
      rent12 = list.sum { |t| t['nr12'].to_i }
      data['doShort'] = do_short
      data['sigungu'] = sg
      data['dong'] = dong
      data['count'] = list.size
      data['rows'] = rows
      data['neighbors'] = neighbors
      top_trades = list.flat_map { |t| (t['tg'] || []).map { |g| [g['max3'], t['name'], g, t] } }.max_by(3) { |x| x[0] }
      top_trades = [] if top_trades.nil?
      data['topList'] = top_trades.map { |amt, name, g, t| { 'name' => name, 'label' => TradeFmt.area_label(g['a'], g['py']), 'amt' => TradeFmt.man(amt), 'date' => TradeFmt.ymd(g['max3d']) } }
      hi = list.sum { |t| (t['hi'] || []).size }
      most = list.max_by { |t| t['n12'].to_i }
      s = +"#{do_short} #{sg} #{dong}에는 실거래가가 신고된 아파트 단지가 #{list.size}곳 있습니다. 최근 12개월 동안 매매 #{total12}건, 전월세 #{rent12}건이 신고됐습니다."
      s << " 거래가 가장 많은 단지는 #{most['name']}(매매 #{most['n12']}건)입니다." if most && most['n12'].to_i.positive?
      s << " 최근 30일 안에 3년 내 최고가를 경신한 신고가 거래가 #{hi}건 있습니다." if hi.positive?
      data['summary'] = s
      data['faq'] = [
        { 'q' => "#{dong} 아파트 실거래가는 어디서 확인하나요?", 'a' => "아래 단지 목록에서 단지를 선택하면 평형별 최근 거래가, 최고·최저가, 전세·월세 시세를 볼 수 있습니다. 국토교통부 실거래가 공개시스템의 신고 자료입니다." },
        { 'q' => "#{dong}에는 아파트 단지가 몇 곳 있나요?", 'a' => "실거래 신고 이력이 있는 단지 기준 #{list.size}곳입니다. 최근 12개월 매매 신고는 #{total12}건입니다." }
      ]
      seo("#{sg} #{dong} 아파트 실거래가 - 단지 #{list.size}곳 매매·전세 시세", "#{do_short} #{sg} #{dong} 아파트 #{list.size}개 단지의 실거래가와 전세·월세 시세. 최근 12개월 매매 #{total12}건 신고. 단지별 평형별 최고·최저가를 확인하세요.")
    end
  end

  # ── 신고가 페이지(전국/시도) ───────────────────────────────
  class ShingogaPage < TradeBasePage
    def initialize(site, scope, rows, meta)
      if scope == '전국'
        setup(site, 'shingoga', 'shingoga')
      else
        setup(site, "shingoga/#{scope}", 'shingoga')
      end
      data['scope'] = scope
      data['rows'] = rows
      data['asOf'] = TradeFmt.ymd(meta['latest'] || 0)
      data['count'] = rows.size
      seo("#{scope == '전국' ? '전국' : scope} 아파트 신고가 - 최근 30일 최고가 경신 거래 #{rows.size}건", "#{scope} 아파트 중 최근 30일 안에 3년 내 최고가를 경신한 신고가 거래 #{rows.size}건. 단지·평형·층·직전 최고가와의 차이를 확인하세요.")
    end
  end

  class TradeHubGenerator < Generator
    safe true
    priority :normal

    MIN_COMPLEXES_DONG = 2

    def generate(site)
      all = site.data['trade_all'] || []
      return if all.empty?
      meta = site.data['trade_meta'] || {}

      # 실거래 전용 단지 페이지
      only = site.data['trade_only'] || []
      only.each { |t| site.pages << TradeOnlyPage.new(site, t, meta) }

      # 단지 URL
      url_of = lambda do |t|
        t['code'].to_s.empty? ? "/trade/#{TradeGenerator.slug_of(t)}/" : "/apt/#{t['slug']}/"
      end

      # 동 허브
      count = 0
      by_dong = all.group_by { |t| [t['doShort'], t['sigungu'], t['dong']] }
      by_sg = all.group_by { |t| [t['doShort'], t['sigungu']] }
      by_dong.each do |(do_short, sg, dong), list|
        next if list.size < MIN_COMPLEXES_DONG
        rows = list.sort_by { |t| [-t['n12'].to_i, t['name']] }.first(80).map { |t| TradeText.row(t, url_of.call(t)) }
        neighbors = by_dong.select { |(d, s, _), l| d == do_short && s == sg && l.size >= MIN_COMPLEXES_DONG }
                           .map { |(_, _, dg), l| [dg, l.sum { |t| t['n12'].to_i }] }.reject { |dg, _| dg == dong }
                           .sort_by { |dg, n| [-n, dg] }.first(12).map { |dg, n| { 'name' => dg, 'n12' => n } }
        site.pages << TradeDongPage.new(site, do_short, sg, dong, list, rows, neighbors, meta)
        count += 1
      end

      # 시군구 페이지에 얹을 동 목록·상위 단지(기존 SigunguPage 데이터에 주입)
      site.data['trade_sg'] = {}
      by_sg.each do |(do_short, sg), list|
        dongs = list.group_by { |t| t['dong'] }.select { |_, l| l.size >= MIN_COMPLEXES_DONG }
                    .map { |dg, l| { 'name' => dg, 'count' => l.size, 'n12' => l.sum { |t| t['n12'].to_i } } }.sort_by { |h| [-h['n12'], h['name']] }
        hot = list.sort_by { |t| [-t['n12'].to_i, t['name']] }.first(12).map { |t| TradeText.row(t, url_of.call(t)) }
        hi = shingoga_rows(list, url_of)
        site.data['trade_sg']["#{do_short}|#{sg}"] = { 'dongs' => dongs, 'hot' => hot, 'hi' => hi.first(10), 'n12' => list.sum { |t| t['n12'].to_i }, 'cnt' => list.size }
      end

      # 신고가 페이지
      hi_all = shingoga_rows(all, url_of)
      site.pages << ShingogaPage.new(site, '전국', hi_all.first(300), meta)
      all.group_by { |t| t['doShort'] }.each do |do_short, list|
        rows = shingoga_rows(list, url_of)
        site.pages << ShingogaPage.new(site, do_short, rows.first(200), meta)
      end
      site.data['shingoga_top'] = hi_all.first(10)

      # 홈 검색용 추가 색인(실거래 전용 단지 + 동 허브)
      idx = only.map { |t| { 'n' => t['name'], 'do' => t['doShort'], 'sg' => t['sigungu'], 'u' => "/trade/#{TradeGenerator.slug_of(t)}/" } }
      by_dong.each do |(do_short, sg, dong), list|
        next if list.size < MIN_COMPLEXES_DONG
        idx << { 'n' => "#{dong} 아파트 실거래가", 'do' => do_short, 'sg' => sg, 'u' => "/region/#{do_short}/#{sg}/#{dong}/" }
      end
      pg = PageWithoutAFile.new(site, site.source, '', 'search_trade.json')
      pg.content = JSON.generate(idx)
      pg.data['layout'] = nil
      pg.data['sitemap'] = false
      site.pages << pg
      Jekyll.logger.info 'TradeGenerator:', "동 허브 #{count} / 전용 단지 #{only.size} / 신고가 #{hi_all.size}건"
    end

    # 최근 30일 신고가 이벤트 행(금액 큰 순)
    def shingoga_rows(list, url_of)
      rows = []
      list.each do |t|
        (t['hi'] || []).each do |h|
          rows << { 'amtN' => h['amt'], 'name' => t['name'], 'url' => url_of.call(t), 'loc' => "#{t['doShort']} #{t['sigungu']} #{t['dong']}",
                    'area' => TradeFmt.area_label(h['a'], (h['a'] * 1.32 / 3.3058).round), 'amt' => TradeFmt.man(h['amt']), 'prev' => TradeFmt.man(h['prev']),
                    'diff' => TradeFmt.man(h['amt'] - h['prev']), 'date' => TradeFmt.ymd(h['d']), 'floor' => h['f'], 'dateN' => h['d'] }
        end
      end
      rows.sort_by { |r| [-r['dateN'], -r['amtN']] }
    end
  end

  module TradeGenerator
    def self.slug_of(t)
      base = t['name'].to_s.gsub(/[^\p{Hangul}\p{Alnum}]+/, '-').gsub(/-+/, '-').gsub(/\A-|-\z/, '')[0, 22]
      "#{base}-#{t['seq']}".gsub(/-+/, '-')
    end
  end
end

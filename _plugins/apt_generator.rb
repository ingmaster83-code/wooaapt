require 'json'

module Jekyll
  module AptUtil
    def self.load_json(site, path)
      file = File.join(site.source, path)
      return [] unless File.exist?(file)
      JSON.parse(File.read(file, encoding: 'utf-8'))
    rescue => e
      Jekyll.logger.warn "AptGenerator:", "#{path} 로드 실패: #{e.message}"
      []
    end

    def self.rawdata_dir(site)
      File.join(site.source, '_rawdata')
    end
  end

  # ── 데이터 로드 (한 번만) ──────────────────────────────
  class AptDataGenerator < Generator
    safe true
    priority :highest

    def generate(site)
      return if site.data['apt_all']

      dir = AptUtil.rawdata_dir(site)
      shard_files = Dir.glob(File.join(dir, 'apts_*.json'))
      all_apts = []
      by_do = Hash.new { |h, k| h[k] = [] }

      shard_files.each do |f|
        do_short = File.basename(f, '.json').sub('apts_', '')
        items = JSON.parse(File.read(f, encoding: 'utf-8'))
        by_do[do_short] = items
        all_apts.concat(items)
      end

      site.data['apt_all'] = all_apts
      site.data['apt_by_do'] = by_do
      Jekyll.logger.info "AptGenerator:", "총 #{all_apts.size}개 단지 로드 (#{by_do.size}개 시도)"
    end
  end

  # ── 시도 인덱스 페이지 ─────────────────────────────────
  class DoIndexPageGenerator < Generator
    safe true
    priority :normal

    def generate(site)
      by_do = site.data['apt_by_do'] || {}
      by_do.each do |do_short, apts|
        site.pages << DoIndexPage.new(site, do_short, apts)
      end
      Jekyll.logger.info "AptGenerator:", "시도 페이지 #{by_do.size}개 생성"
    end
  end

  class DoIndexPage < Page
    def initialize(site, do_short, apts)
      @site = site
      @base = site.source
      @dir  = "region/#{do_short}"
      @name = 'index.html'
      self.process(@name)
      self.read_yaml(File.join(@base, '_layouts'), 'do.html')

      by_sigungu = Hash.new(0)
      apts.each { |a| by_sigungu[a['sigungu']] += 1 }
      sigungu_list = by_sigungu.map { |name, cnt| { 'name' => name, 'count' => cnt } }.sort_by { |s| -s['count'] }

      self.data['doShort'] = do_short
      self.data['sigunguList'] = sigungu_list
      self.data['totalCount'] = apts.size
      self.data['layout'] = 'do'
      self.data['title'] = "#{do_short} 아파트 단지정보 — 시군구별 목록"
      self.data['description'] = "#{do_short} 지역 아파트 #{apts.size}개 단지 정보를 시군구별로 확인하세요."
    end
  end

  # ── 시군구 페이지 ──────────────────────────────────────
  class SigunguPageGenerator < Generator
    safe true
    priority :normal

    def generate(site)
      by_do = site.data['apt_by_do'] || {}
      count = 0
      by_do.each do |do_short, apts|
        grouped = Hash.new { |h, k| h[k] = [] }
        apts.each { |a| grouped[a['sigungu']] << a }
        grouped.each do |sigungu, list|
          site.pages << SigunguPage.new(site, do_short, sigungu, list)
          count += 1
        end
      end
      Jekyll.logger.info "AptGenerator:", "시군구 페이지 #{count}개 생성"
    end
  end

  class SigunguPage < Page
    def initialize(site, do_short, sigungu, apts)
      @site = site
      @base = site.source
      @dir  = "region/#{do_short}/#{sigungu}"
      @name = 'index.html'
      self.process(@name)
      self.read_yaml(File.join(@base, '_layouts'), 'sigungu.html')

      self.data['doShort'] = do_short
      self.data['sigungu'] = sigungu
      self.data['apts'] = apts.sort_by { |a| a['aptName'] }
      self.data['totalCount'] = apts.size
      self.data['layout'] = 'sigungu'
      self.data['title'] = "#{do_short} #{sigungu} 아파트 단지 목록 (#{apts.size}개)"
      self.data['description'] = "#{do_short} #{sigungu} 아파트 #{apts.size}개 단지의 세대수, 관리비, 기본정보를 확인하세요."
    end
  end

  # ── 개별 단지 상세 페이지 ──────────────────────────────
  class AptPageGenerator < Generator
    safe true
    priority :normal

    def generate(site)
      all_apts = site.data['apt_all'] || []
      all_apts.each { |a| site.pages << AptPage.new(site, a) }
      Jekyll.logger.info "AptGenerator:", "단지 상세 페이지 #{all_apts.size}개 생성"
    end
  end

  class AptPage < Page
    def initialize(site, a)
      @site = site
      @base = site.source
      @dir  = "apt/#{a['slug']}"
      @name = 'index.html'
      self.process(@name)
      self.read_yaml(File.join(@base, '_layouts'), 'apt.html')
      self.data.merge!(a)
      self.data['layout'] = 'apt'
      self.data['title'] = "#{a['aptName']} 정보 — 세대수·관리비·기본정보 | #{a['doShort']} #{a['sigungu']}"
      desc_bits = []
      desc_bits << "#{a['hoCnt'].to_i}세대" if a['hoCnt']
      desc_bits << "#{a['dongCnt']}개동" if a['dongCnt']
      desc_bits << a['heatType'] if a['heatType']
      extra = desc_bits.empty? ? '' : " (#{desc_bits.join(' · ')})"
      self.data['description'] = "#{a['doShort']} #{a['sigungu']} #{a['aptName']}#{extra} 기본정보와 관리비를 확인하세요."
    end
  end
end

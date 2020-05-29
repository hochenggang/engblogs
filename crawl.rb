# Crawl feeds from OPML file and build a page
# to display the resulting items on.

require 'dotenv'
Dotenv.load
require 'aws-sdk-dynamodb'
require 'aws-sdk-s3'
require 'feedjira'
require 'thread/pool'
require 'digest/sha1'
require 'erb'
require 'open-uri'


# -------------------
# STEP ONE: READ AND PARSE OPML FILE
# -------------------

opml = URI.open("http://#{ENV['S3_BUCKET_NAME']}.s3.#{ENV['AWS_DEFAULT_REGION']}.amazonaws.com/#{ENV['S3_BUCKET_NAME']}.opml").read

# Can't be bothered with the dependencies, so let's go oldschool..
feeds = opml.scan(/<outline.*\/>/)
feeds.map! do |feed|
  {
    title: feed[/title=(\"|\')(.*?)\1/i, 2],
    xmlurl: feed[/xmlurl=(\"|\')(.*?)\1/i, 2],
    htmlurl: feed[/htmlurl=(\"|\')(.*?)\1/i, 2],
  }
end


# -------------------
# STEP TWO: CRAWL ALL THE FEEDS AND GET THE ITEMS
# -------------------

pool = Thread.pool(20)
semaphore = Mutex.new
dynamodb = Aws::DynamoDB::Client.new

feeds.each do |feed|
  pool.process do
    STDERR.puts "Doing #{feed[:title]}"

    # Fetch the feed. If we can't, fail.
    begin
      xml = URI.open(feed[:xmlurl], :open_timeout => 5, :read_timeout => 10, "User-Agent" => "My RSS Reader" ).read
    rescue Net::OpenTimeout, OpenSSL::SSL::SSLError, SocketError, OpenURI::HTTPError, URI::InvalidURIError => e
      STDERR.puts "  FAILURE #{e}"
      next
    end

    # Parse the feed. If we can't, fail.
    begin
      pfeed = Feedjira.parse(xml)
    rescue Feedjira::NoParserAvailable
      STDERR.puts "  FAILURE"
      next
    end

    entries = pfeed.entries.map do |entry|
      {
        published: entry.published,
        title: entry.title.to_s.strip,
        url: entry.url.to_s.strip,
        feed: feed[:title],
        feed_site: feed[:htmlurl]
      }
    end

    # We only want items that are less than 8 days old
    entries = entries.select { |entry| (Time.now - entry[:published]) < (86400 * 8) }

    STDERR.puts "  Fetched #{pfeed.entries.size} entries, #{entries.size} recent"

    # Put items into DynamoDB
    semaphore.synchronize do      
      entries.each do |entry|
        t = entry[:published]
        params = {
          table_name: ENV['DYNAMODB_TABLE_NAME'],
          item: {
            date: t.strftime("%Y-%m-%d"),
            hash: Digest::SHA1.hexdigest(entry[:url]),
            ttl: t.to_i + (86400 * 7) + 3600
          }
        }
        params[:item].merge!(entry)
        params[:item][:published] = params[:item][:published].to_s

        begin
          dynamodb.put_item(params)
          STDERR.puts "Added"
        rescue  Aws::DynamoDB::Errors::ServiceError => error
          STDERR.puts "ERROR"
          STDERR.puts error.message
        end
      end
    end
  end
end

pool.shutdown 


# -------------------
# STEP THREE: BUILD THE OUTPUT JSON AND HTML
# -------------------

s3 = Aws::S3::Client.new(region: ENV['AWS_DEFAULT_REGION'])

# We can scan because we're using DynamoDB's TTL feature to automatically
# cull old entries.
result = dynamodb.scan(table_name: ENV['DYNAMODB_TABLE_NAME'])
items = result.items.sort_by { |r| r['published'] }.reverse

# Write out a JSON with all the items and store on S3
s3.put_object(bucket: ENV['S3_BUCKET_NAME'], key: 'entries.json', body: items.to_json, content_type: 'application/json', cache_control: "max-age=3600")
s3.put_object_acl({ acl: "public-read", bucket: ENV['S3_BUCKET_NAME'], key: 'entries.json' })

# Map items into a slightly more useful structure for ERB
items = items.map do |item|
  {
    published: Time.parse(item['published']),
    title: item['title'],
    url: item['url'],
    feed: item['feed'],
    feed_site: item['feed_site']
  }
end

# Write out an HTML file with all the items rendered through our template
res = ERB.new(File.read("template.erb")).result(binding)
s3.put_object(bucket: ENV['S3_BUCKET_NAME'], key: 'index.html', body: res, content_type: 'text/html;charset=utf-8', cache_control: "max-age=3600")
s3.put_object_acl({ acl: "public-read", bucket: ENV['S3_BUCKET_NAME'], key: 'index.html' })


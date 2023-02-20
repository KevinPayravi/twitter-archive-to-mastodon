*This script is heavily derived from **[lucahammer's fediporter](https://github.com/lucahammer/fediporter)** Python Notebook. 98% of the script was written by lucahammer; I've simplified and adjusted some things to run more reliably for myself, and figured I'd share it here (along with my rate-limiting mods) if it's helpful for anyone. Thank you Luca for the script!*

----

# twitter-archive-to-mastodon

This is a server-side Python3 script you can use to import your [Twitter archive](https://help.twitter.com/en/managing-your-account/how-to-download-your-twitter-archive) into a Mastodon instance you are running and have server access to. With mods to your Mastodon instance, you can remove rate limiting, have your toots backdated, and not push these toots out to your followers (because that would probably annoy them).

When migrating archived Tweets to Mastodon, this script will do the following:
* Upload media
* Replace @username with @username@twitter.com
* Threads are recreated as threads (Luca noted that this is fragile, though it seemed to work reliably for me)
* Embedded t.co URLs are replaced with the expanded versions
* Retweets are skipped (I figure you wouldn't want these on your profile anyway)
* Replies and tweets that start with "@" are skipped

Limitations:
* I have no idea what happens if the script comes across a poll.
* Alt text is not included since the archive doesn't include them
  * Luca was working on fetching alt text from Twitter in his notebook
* Edit history isn't imported

Using this script, I was successfully able to import 2,300+ tweets from all the way back in 2010.

Note that I don't plan to actively maintain or expand this script, but feel free to open PRs.

## Mod Mastodon

The first few mods are to add a "created_at" parameter to the status-posting API. The second set of mods is to remove rate-limiting.

⚠️ You can and should revert these changes after you're done importing! Leaving disabled and/or ridiculously high rate limits makes your instance suspectible to attack. ⚠️

After modding, you need to restart the daemon and Mastodon with the following commands:
```
systemctl daemon-reload
sudo systemctl restart mastodon-*
```

----

### In `app/controllers/api/v1/statuses_controller.rb`:

In `PostStatusService`, add `created_at: status_params[:created_at],` and set `with_rate_limit` to `false`:
```rb
  def create
    @status = PostStatusService.new.call(
      current_user.account,
      text: status_params[:status],
      thread: @thread,
      media_ids: status_params[:media_ids],
      sensitive: status_params[:sensitive],
      spoiler_text: status_params[:spoiler_text],
      visibility: status_params[:visibility],
      language: status_params[:language],
      scheduled_at: status_params[:scheduled_at],
      created_at: status_params[:created_at],
      application: doorkeeper_token.application,
      poll: status_params[:poll],
      idempotency: request.headers['Idempotency-Key'],
      with_rate_limit: false
    )
```
 
In `status_params`, add `:created_at,`:
 
 ```rb
   def status_params
    params.permit(
      :status,
      :in_reply_to_id,
      :sensitive,      :spoiler_text,      :visibility,
      :language,
      :scheduled_at,
      :created_at,
      media_ids: [],
      poll: [
        :multiple,
        :hide_totals,
        :expires_in,
        options: [],
      ]
    )
  end
```

----

### In `app/services/post_status_service.rb`:

Wrap the `DistributionWorker` and `ActivityPub` lines in an if-statement checking for `:created_at`:

```rb
  def postprocess_status!
    Trends.tags.register(@status)il  LinkCrawlWorker.perform_async(@status.id)
    if not @options[:created_at]
      DistributionWorker.perform_async(@status.id)
      ActivityPub::DistributionWorker.perform_async(@status.id)
    end
    PollExpirationNotifyWorker.perform_at(@status.poll.expires_at, @status.poll.id) if @status.poll
  end
```

In `status_attributes`, add `created_at: @options[:created_at],`:
```rb
  def status_attributes
    {
      text: @text,
      created_at: @options[:created_at],
      media_attachments: @media || [],
      ordered_media_attachment_ids: (@options[:media_ids] || []).map(&:to_i) & @media.map(&:id),
      thread: @in_reply_to,
      poll_attributes: poll_attributes,
      sensitive: @sensitive,
      spoiler_text: @options[:spoiler_text] || '',
      visibility: @visibility,
      language: valid_locale_cascade(@options[:language], @account.user&.preferred_posting_language, I18n.default_locale),
      application: @options[:application],
      rate_limit: @options[:with_rate_limit],
    }.compact
  end
```

### In `app/lib/rate_limiter.rb`:

Increases the `statuses` rate limit to something absurd. Example (changed `300` to `300000`):
```rb
    statuses: {
      limit: 300000,
      period: 3.hours.freeze,
    }.freeze,
```

In `config/initializers/rack_attack.rb`...

There are some API-related throttles towards the bottom. Example:
```rb
  throttle('throttle_authenticated_api', limit: 1_500, period: 5.minutes) do |req|
    req.authenticated_user_id if req.api_request?
  end
```

I changed `throttle_authenticated_api`, `throttle_per_token_api`, `throttle_api_media`, `throttle_media_proxy` to absurd numbers (`300000` or whatever).

----

⚠️ You can and should revert these changes after you're done importing! Leaving disabled and/or ridiculously high rate limits makes your instance suspectible to attack. ⚠️

After modding, you need to restart the daemon and Mastodon with the following commands:
```
systemctl daemon-reload
sudo systemctl restart mastodon-*
```

----

### Running

#### Transfer archive
You'll need your Twitter archive on your server. I use [FileZilla](https://filezilla-project.org/) for easy and reliable transferring.

You'll need to unzip your archive once it's on the server.

#### Configs

Near the top of `import.py` are some variables you need to update:
* `API_BASE_URL` is the URL of your Mastodon instance (e.g. `https://example.com`)
* `MASTODON_ACCESS_TOKEN` is your private API access token you need to post toots. You can get a token by going to Preferences -> Development -> New Application. Specify your application name (which will show up below your imported toots) and, optionally, a link (I put my Twitter profile link).
* `DATA_DIR` is the location of your unzipped Twitter archive. Needs a trailing slash.
* `MEDIA_DIR` is the location of your Twitter archive's media folder (`/tweets_media`). Needs a trailing slash.
* `TWITTER_USERNAME` is your Twitter username (no @). This is used to track your threads.
* 
#### Dependencies
Have Python3 and Pip installed.

Using pip, install `requests`, `tqdm`, and `ipywidgets`

#### Run
After updating the configs and installing the dependencies, simply run `python3 import.py` and hopefully it works!

The script will output Tweet data as it runs.

email_body = """
<!DOCTYPE html>
<html lang="en">
  <head>
    <meta charset="UTF-8" />
  </head>

  <body style="font-family: Inter, sans-serif; font-size: 14px">
    <div
      class="email-card"
      style="width: 100%; margin: 0 auto; max-width: 520px"
    >
      <div style="display: flex; justify-content: center">
        <img
          height="140px"
          src="https://dev.datapoem.ai/icons/email/girl-notif.png"
        />
      </div>
      <div
        class="header"
        style="
          display: flex;
          justify-content: center;
          background: #fff;
          padding: 0px 30px;
        "
      >
        <div>
          <h1>Data Hub Notification - {actiontype} - {env}</h1>
        </div>
      </div>
      <div
        class="main"
        style="
          padding: 40px 30px 35px 30px;
          border-radius: 20px 20px 0px 0px;
          border-top: 1px solid rgba(28, 28, 28, 0.4);
        "
      >
        <p>Dear Data Team,</p>

        <h4
          style="
            border-bottom: 1px solid rgba(28, 28, 28, 0.4);
            padding-bottom: 22px;
          "
        >
          An action has been performed on the file vault and is now available
          for review.
        </h4>

        <div class="ticket-meta" style="padding-bottom: 27px">
          <div class="bold" style="font-weight: bold">
            <h2>File details:</h2>
          </div>
          <div>
            <span class="bold" style="font-weight: bold">File name : </span>
            <span> {filename} </span>
          </div>
          <div>
            <span class="bold" style="font-weight: bold">File path : </span>
            <span> {path} </span>
          </div>
          <div>
            <span class="bold" style="font-weight: bold">Action : </span>
            <span> {action} </span>
          </div>
          <div>
            <span class="bold" style="font-weight: bold">Timestamp : </span>
            <span> {timestamp} </span>
          </div>
          <div>
            <span class="bold" style="font-weight: bold">Author : </span>
            <span> {author} </span>
          </div>
        </div>

        <div style="border-top: 1px solid rgba(28, 28, 28, 0.4)"></div>
        <div class="footer-logo" style="display: flex">
          <div>
            <div>Best regards,</div>
            <div style="margin-top: 10px">
              <img
                height="60px"
                src="https://datapoem.ai/icons/email/logo.png"
              />
            </div>
          </div>
        </div>
        <div>
          <p style="font-size: 12px">
            <i>
              This is a system generated email. Please do not reply to this
              message.
            </i>
          </p>
        </div>
      </div>
    </div>
  </body>
</html>

"""

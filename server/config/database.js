const mongoose = require('mongoose')
require('dotenv').config();

exports.connect = () =>{
    mongoose.connect(process.env.MONGOOSE_URL)
    .then(() => console.log("DB Connection successful"))
    .catch((err) => {console.log("DB Connection failed");
                    console.error(err);
                process.exit(1);})
};
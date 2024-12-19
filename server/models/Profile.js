const mongoose = require('mongoose');

const profileSchema = mongoose.Schema({
    gender:{
        type:String
    },
    about:{
        type:String,
        trim:true
    },
    datOfBirth:{
        type:String
    },
    contactNumber:{
        type:Number,
        trim:true
    }
});

module.exports = mongoose.model("Profile",profileSchema);
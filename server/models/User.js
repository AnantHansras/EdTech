const mongoose = require('mongoose');

const userSchema = mongoose.Schema({
    firstName :{
        type:String,
        required:true,
        trim:true
    },
    lastName :{
        type:String,
        required:true,
        trim:true
    },
    email :{
        type:String,
        required:true,
        trim:true
    },
    password :{
        type:String,
        required:true
    },
    accountType :{
        type:String,
        required:true,
        enum:["Student","Admin","Instructor"]
    },
    additionalDetails :{
        type: mongoose.Schema.Types.ObjectId,
        required:true,
        ref:"Profile"
    },
    active: {
			type: Boolean,
			default: true,
		},
    approved: {
			type: Boolean,
			default: true,
	},
    courses:[
        {
            type:mongoose.Schema.Types.ObjectId,
            ref:"Course"
        }
    ],
    image :{
        type:String,
        required:true
    },
    courseProgress :[
        {
            type:mongoose.Schema.Types.ObjectId,
            ref:"courseProgress"
        }
    ],
    token:{
        type:String
    },
    resetPasswordExpires:{
        type:Date
    }
});

module.exports = mongoose.model("User",userSchema);